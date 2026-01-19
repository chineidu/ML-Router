import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import anyio
import httpx

from src import create_logger
from src.schemas.backend_registry import ServiceInstance
from src.schemas.types import ModelTypeEnum, StatusEnum
from src.services.docker_service_discovery import DockerServiceDiscovery

logger = create_logger(name=__name__)


class ServiceRegistry:
    """File-based service registry for service discovery.

    This implementation is for learning and testing purposes only. In production,
    use a robust service discovery mechanism like Consul, etcd, or Kubernetes.
    """

    REGISTRY_DIR_PATH: str = "data"
    DOCKER_REGISTRY_FILENAME: str = "docker_registry.json"

    def __init__(
        self,
        registry_file: str | None,
        load_registry_from_file: bool = True,
        health_check_interval: int = 10,
    ) -> None:
        self.load_registry_from_file = load_registry_from_file
        if load_registry_from_file and not registry_file:
            raise ValueError(
                "Registry file path must be provided if load_registry_from_file is True."
            )
        if load_registry_from_file and registry_file:
            self.registry_file: Path | None = Path(registry_file)
            logger.info(f"Using service registry file at: {self.registry_file}")
        else:
            self.registry_file = None
        self.registry: dict[str, ServiceInstance] = {}
        self.health_check_interval = health_check_interval  # seconds
        self.registry_save_path: Path | None = None
        self._lock = asyncio.Lock()

    async def ainitialize(self) -> None:
        """Initialize the registry by loading from disk and performing an initial health check."""
        await self._aload_registry()
        await self._create_registry_dir(
            dir_path=Path(self.REGISTRY_DIR_PATH)
        )  # Ensure directory exists
        # Perform initial health check to mark services as healthy immediately
        await self._acheck_all_health()
        logger.info("Service registry initialized.")

    async def _create_registry_dir(self, dir_path: Path) -> None:
        """Creates the registry directory if it doesn't exist and sets the registry save path."""
        await anyio.Path(dir_path).mkdir(parents=True, exist_ok=True)
        # Set registry save path to a file, not directory
        self.registry_save_path = dir_path / self.DOCKER_REGISTRY_FILENAME

    async def _asave_as_json(self, data: Any, indent: int = 2) -> None:
        """Saves data as JSON to the specified path."""
        if not self.registry_save_path:
            logger.warning("Registry save path is not set. Cannot save registry.")
            return
        await anyio.Path(self.registry_save_path).write_text(
            json.dumps(data, indent=indent)
        )

    async def _aload_registry_from_file(self) -> None:
        """Loads the service registry from the file."""
        if not self.load_registry_from_file or not self.registry_file:
            raise ValueError(
                "Registry file path must be set to load registry from file."
            )

        registry_path = anyio.Path(self.registry_file)
        if await registry_path.exists():
            try:
                text = await registry_path.read_text()
                services = json.loads(text)
                self.registry = {
                    svc_id: ServiceInstance(**svc_data)
                    for svc_id, svc_data in services.items()
                }
                logger.info(f"Loaded {len(self.registry)} services from registry.")
            except Exception as e:
                logger.error(f"Error loading service registry: {e}")
                self.registry = {}
        else:
            logger.warning(
                f"Registry file {self.registry_file} does not exist. Starting with empty registry."
            )
            self.registry = {}

    async def _aload_registry_from_docker(self) -> None:
        """Discovers services from Docker and loads them into the registry."""
        project = os.getenv("COMPOSE_PROJECT_NAME", "ml-router")
        dsd = DockerServiceDiscovery(compose_project_name=project)

        try:
            services = await dsd.adiscover_model_services()

            if len(services) == 0:
                logger.warning(
                    f"No Docker services found for project '{project}'. Trying without project filter..."
                )
                # Try without project name filter
                dsd_no_filter = DockerServiceDiscovery(compose_project_name=None)
                services = await dsd_no_filter.adiscover_model_services()

            if len(services) == 0:
                raise RuntimeError("No Docker services found for discovery.")

            self.registry = services  # Services are already ServiceInstance objects
            logger.info(f"Loaded {len(self.registry)} services from Docker discovery.")
        except Exception as e:
            logger.error(f"Error loading service registry from Docker: {e}")
            raise

    async def _aload_registry(self) -> None:
        """Loads the service registry from the file or Docker."""
        if self.load_registry_from_file:
            await self._aload_registry_from_file()
        else:
            await self._aload_registry_from_docker()

    async def _asave_registry(self) -> None:
        """Saves the service registry to disk."""
        if not self.registry_save_path:
            logger.warning("Registry save path is not set. Cannot save registry.")
            return
        try:
            data: dict[str, dict[str, Any]] = {
                svc_id: instance.model_dump()
                for svc_id, instance in self.registry.items()
            }
            await self._asave_as_json(data, indent=2)
        except (OSError, PermissionError) as e:
            logger.warning(
                f"Unable to save registry to {self.registry_save_path}: {e}. "
                f"Registry updates will not persist."
            )

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
                instance.last_heartbeat = time.time()
                instance.status = StatusEnum.HEALTHY
                logger.info(
                    f"Health check passed for service '{instance.service_name}' [{service_id}]"
                )
            else:
                instance.status = StatusEnum.UNHEALTHY
                logger.warning(
                    f"Health check returned {response.status_code} for service "
                    f"'{instance.service_name}' [{service_id}]"
                )

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
        logger.info("Backend registry initialized.")

    async def aget_endpoint(self, model_type: ModelTypeEnum | str) -> str | None:
        """Get the endpoint URL of an available backend for the given model type."""
        model_type = (
            model_type
            if isinstance(model_type, ModelTypeEnum)
            else ModelTypeEnum(model_type)
        )
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
        self, model_type: ModelTypeEnum | str
    ) -> list[ServiceInstance]:
        """Get all healthy backend instances for the given model type."""
        model_type = (
            model_type
            if isinstance(model_type, ModelTypeEnum)
            else ModelTypeEnum(model_type)
        )
        service_name = model_type.value
        return await self.service_registry.aget_healthy_instances(service_name)
