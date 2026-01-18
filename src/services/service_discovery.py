import asyncio
import json
import time
from pathlib import Path
from typing import Any

import anyio
import httpx

from src import create_logger
from src.schemas.backend_registry import ServiceInstance
from src.schemas.types import ModelTypeEnum, StatusEnum

logger = create_logger(name="services.service_discovery")


class ServiceRegistry:
    """File-based service registry for service discovery.

    This implementation is for learning and testing purposes only. In production,
    use a robust service discovery mechanism like Consul, etcd, or Kubernetes.
    """

    def __init__(self, registry_file: str = "/tmp/service_registry.json") -> None:
        self.registry_file = Path(registry_file)
        self.registry: dict[str, ServiceInstance] = {}
        self.health_check_interval = 10  # seconds
        self._lock = asyncio.Lock()

    async def ainitialize(self) -> None:
        """Initialize the registry by loading from disk."""
        await self._aload_registry()
        logger.info("Service registry initialized.")

    async def _aload_registry(self) -> None:
        """Loads the service registry from the file."""
        registry_path = anyio.Path(self.registry_file)
        if await registry_path.exists():
            try:
                text = await registry_path.read_text()
                data = json.loads(text)
                self.registry = {
                    svc_id: ServiceInstance(**svc_data)
                    for svc_id, svc_data in data.items()
                }
            except Exception as e:
                logger.error(f"Error loading service registry: {e}")
                self.registry = {}

    async def _asave_registry(self) -> None:
        """Saves the service registry to disk."""
        data: dict[str, dict[str, Any]] = {
            svc_id: instance.model_dump() for svc_id, instance in self.registry.items()
        }
        await anyio.Path(self.registry_file).write_text(json.dumps(data, indent=2))

    async def aregister(self, instance: ServiceInstance) -> None:
        """Register a new service instance."""
        if not self.registry:
            raise ValueError(
                "Service registry not initialized. Call 'ainitialize()' first."
            )

        self.registry[instance.service_id] = instance
        await self._asave_registry()
        logger.info(
            f"Registered service: '{instance.service_name}' [{instance.service_id}] "
            f"at {instance.endpoint_url}"
        )

    async def aderegister(self, service_id: str) -> None:
        """Deregister a service instance."""
        if service_id not in self.registry:
            return

        async with self._lock:
            # Thread-safe removal (prevents race conditions)
            if service_id in self.registry:
                # Remove the service from the registry
                instance = self.registry.pop(service_id)
                await self._asave_registry()
                logger.info(
                    f"Deregistered service: '{instance.service_name}' [{service_id}]"
                )
            else:
                logger.warning(
                    f"Service ID {service_id} not found in registry for deregistration."
                )

    async def aheartbeat(self, service_id: str) -> None:
        """Update the last heartbeat timestamp for a service instance."""
        if service_id not in self.registry:
            return

        async with self._lock:
            # Thread-safe update (prevents race conditions)
            if service_id in self.registry:
                instance = self.registry[service_id]
                instance.last_heartbeat = time.time()
                self.registry[service_id].status = StatusEnum.HEALTHY
                await self._asave_registry()
                logger.debug(
                    f"Heartbeat received for service: '{instance.service_name}' [{service_id}]"
                )
            else:
                logger.warning(
                    f"Service ID {service_id} not found in registry for heartbeat."
                )

    async def aget_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
        """Get all healthy service instances."""
        return [
            inst
            for inst in self.registry.values()
            if inst.service_name == service_name
            and inst.status == StatusEnum.HEALTHY
            and not inst.is_stale
        ]

    async def ahealth_check_loop(self) -> None:
        """Periodically check the health of registered services."""
        while True:
            await self._acheck_all_health()
            await asyncio.sleep(self.health_check_interval)

    async def _acheck_single_health(
        self, aclient: httpx.AsyncClient, service_id: str
    ) -> None:
        """Check health of a registered services and update its status."""
        instance: ServiceInstance = self.registry[service_id]
        try:
            response = await aclient.get(instance.health_check_url)
            if response.status_code == 200:
                instance.status = StatusEnum.HEALTHY
            else:
                instance.status = StatusEnum.UNHEALTHY

        except Exception as e:
            logger.warning(
                f"Health check failed for service '{instance.service_name}' [{service_id}]: {e}"
            )
            instance.status = StatusEnum.UNHEALTHY

        if instance.is_stale:
            instance.status = StatusEnum.UNHEALTHY
            logger.warning(
                f"Removing stale service: '{instance.service_name}' [{service_id}]."
            )

            await self.aderegister(service_id)

    async def _acheck_all_health(self) -> None:
        """Check health of all registered services and update their status."""
        async with httpx.AsyncClient(timeout=5) as aclient:
            tasks = [
                self._acheck_single_health(aclient, service_id)
                for service_id in self.registry.keys()
            ]

            # Run health checks concurrently
            await asyncio.gather(*tasks)

        # Save updated statuses
        await self._asave_registry()

    def list_all_services(self) -> dict[str, list[ServiceInstance]]:
        """List all registered service instances grouped by service name."""
        services: dict[str, list[ServiceInstance]] = {}

        for instance in self.registry.values():
            # If services not in dict, initialize list
            if instance.service_name not in services:
                services[instance.service_name] = []
                # Add instance to the list
            services[instance.service_name].append(instance)
        return services


class BackendRegistry:
    """Backend registry using service discovery to discover available ML model backends."""

    def __init__(self, service_registry: ServiceRegistry) -> None:
        self.service_registry = service_registry
        # Creates: {ModelTypeEnum.SENTIMENT: 0, ModelTypeEnum.CLASSIFICATION: 0, ...}
        self.current_idx: dict[ModelTypeEnum, int] = dict.fromkeys(ModelTypeEnum, 0)

    async def aget_endpoint(self, model_type: ModelTypeEnum) -> str | None:
        """Get the endpoint URL of an available backend for the given model type."""
        service_name = model_type.value
        healthy_instances = await self.service_registry.aget_healthy_instances(
            service_name
        )

        if not healthy_instances:
            logger.warning(
                f"No healthy instances found for model type: {model_type.value}"
            )
            return None

        # Simple round-robin load balancing
        idx = self.current_idx[model_type]
        instance = healthy_instances[idx % len(healthy_instances)]

        # Update index for next request. Using modulo to wrap around. i.e. if len=3,
        # and idx was 0, the next idx is 1, etc. The possible idxs are 0,1,2 (len=3)
        self.current_idx[model_type] = (idx + 1) % len(healthy_instances)
        return f"{instance.endpoint_url}/predict"

    async def aget_all_instances(
        self, model_type: ModelTypeEnum
    ) -> list[ServiceInstance]:
        """Get all healthy backend instances for the given model type."""
        service_name = model_type.value
        return await self.service_registry.aget_healthy_instances(service_name)
