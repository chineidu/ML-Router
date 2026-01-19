# """
# Demo script for testing SimpleServiceRegistry
# """

# import asyncio
# import json
# import time
# from pathlib import Path
# from typing import Any

# import anyio
# import httpx

# from src.schemas.backend_registry import ServiceInstance
# from src.schemas.types import ModelTypeEnum, ProtocolEnum, StatusEnum
# from src.services.service_discovery import BackendRegistry, ServiceRegistry, logger


# async def demo() -> None:
#     """Demonstrate the SimpleServiceRegistry functionality"""

#     print("🚀 Starting SimpleServiceRegistry Demo\n")

#     # Create registry
#     registry = ServiceRegistry("./demo_registry.json")
#     await registry.ainitialize()

#     # Create some service instances
#     services = [
#         ServiceInstance(
#             service_id="sentiment-1",
#             service_name="ml-sentiment",
#             host="localhost",
#             port=8001,
#             protocol=ProtocolEnum.HTTP,
#             health_check_url="http://localhost:8001/health",
#             metadata={"version": "1.0"},
#             registered_at=time.time(),
#             last_heartbeat=time.time(),
#         ),
#         ServiceInstance(
#             service_id="sentiment-2",
#             service_name="ml-sentiment",
#             host="localhost",
#             port=8002,
#             protocol=ProtocolEnum.HTTP,
#             health_check_url="http://localhost:8002/health",
#             metadata={"version": "1.0"},
#             registered_at=time.time(),
#             last_heartbeat=time.time(),
#         ),
#         ServiceInstance(
#             service_id="classification-1",
#             service_name="ml-classification",
#             host="localhost",
#             port=8003,
#             protocol=ProtocolEnum.HTTP,
#             health_check_url="http://localhost:8003/health",
#             metadata={"version": "1.0"},
#             registered_at=time.time(),
#             last_heartbeat=time.time(),
#         ),
#     ]

#     # Register services
#     print("📝 Registering services...")
#     for service in services:
#         await registry.aregister(service)

#     # List services
#     print("\n📋 Current services:")
#     all_services = registry.list_all_services()
#     for name, instances in all_services.items():
#         print(f"  {name}: {len(instances)} instances")

#     # Get healthy instances
#     print("\n✅ Healthy sentiment services:")
#     healthy = await registry.aget_healthy_instances("ml-sentiment")
#     for inst in healthy:
#         print(f"  {inst.service_id} at {inst.endpoint_url}")

#     # Start health check loop in background
#     print("\n🔍 Starting health check loop...")
#     health_task = asyncio.create_task(registry.ahealth_check_loop())

#     # Simulate heartbeats
#     print("\n💓 Sending heartbeats...")
#     await registry.aheartbeat("sentiment-1")
#     await registry.aheartbeat("sentiment-2")
#     await registry.aheartbeat("classification-1")

#     # Wait a bit
#     await asyncio.sleep(2)

#     # Deregister one service
#     print("\n🗑️  Deregistering sentiment-2...")
#     await registry.aderegister("sentiment-2")

#     # List again
#     print("\n📋 Services after deregistration:")
#     all_services = registry.list_all_services()
#     for name, instances in all_services.items():
#         print(f"  {name}: {len(instances)} instances")

#     # Stop health check
#     health_task.cancel()
#     try:
#         await health_task
#     except asyncio.CancelledError:
#         pass

#     print("\n✨ Demo completed!")


# services = [
#     ServiceInstance(
#         service_id="sentiment-1",
#         service_name="ml-sentiment",
#         host="localhost",
#         port=8001,
#         protocol=ProtocolEnum.HTTP,
#         health_check_url="http://localhost:8001/health",
#         metadata={"version": "1.0"},
#         registered_at=time.time(),
#         last_heartbeat=time.time(),
#     ),
#     ServiceInstance(
#         service_id="sentiment-2",
#         service_name="ml-sentiment",
#         host="localhost",
#         port=8002,
#         protocol=ProtocolEnum.HTTP,
#         health_check_url="http://localhost:8002/health",
#         metadata={"version": "1.0"},
#         registered_at=time.time(),
#         last_heartbeat=time.time(),
#     ),
#     ServiceInstance(
#         service_id="classification-1",
#         service_name="ml-classification",
#         host="localhost",
#         port=8003,
#         protocol=ProtocolEnum.HTTP,
#         health_check_url="http://localhost:8003/health",
#         metadata={"version": "1.0"},
#         registered_at=time.time(),
#         last_heartbeat=time.time(),
#     ),
# ]


# class ServiceRegistry:
#     """File-based service registry for service discovery.

#     This implementation is for learning and testing purposes only. In production,
#     use a robust service discovery mechanism like Consul, etcd, or Kubernetes.
#     """

#     def __init__(self, registry_file: str = "/tmp/service_registry.json") -> None:
#         self.registry_file = Path(registry_file)
#         self.registry: dict[str, ServiceInstance] = {}
#         self.health_check_interval = 10  # seconds

#     async def ainitialize(self) -> None:
#         """Initialize the registry by loading from disk."""
#         await self._aload_registry()
#         logger.info("Service registry initialized.")

#     async def _aload_registry(self) -> None:
#         """Loads the service registry from the file."""
#         registry_path = anyio.Path(self.registry_file)
#         if await registry_path.exists():
#             try:
#                 text = await registry_path.read_text()
#                 data = json.loads(text)
#                 self.registry = {
#                     svc_id: ServiceInstance(**svc_data)
#                     for svc_id, svc_data in data.items()
#                 }
#             except Exception as e:
#                 logger.error(f"Error loading service registry: {e}")
#                 self.registry = {}

#     async def _asave_registry(self) -> None:
#         """Saves the service registry to disk."""
#         data: dict[str, dict[str, Any]] = {
#             svc_id: instance.model_dump() for svc_id, instance in self.registry.items()
#         }
#         await anyio.Path(self.registry_file).write_text(json.dumps(data, indent=2))

#     async def aregister(self, instance: ServiceInstance) -> None:
#         """Register a new service instance."""
#         if not self.registry:
#             raise ValueError(
#                 "Service registry not initialized. Call 'ainitialize()' first."
#             )

#         self.registry[instance.service_id] = instance
#         await self._asave_registry()
#         logger.info(
#             f"Registered service: '{instance.service_name}' [{instance.service_id}] "
#             f"at {instance.endpoint_url}"
#         )

#     async def aderegister(self, service_id: str) -> None:
#         """Deregister a service instance."""
#         if service_id in self.registry:
#             # Remove the service from the registry
#             instance = self.registry.pop(service_id)
#             await self._asave_registry()
#             logger.info(
#                 f"Deregistered service: '{instance.service_name}' [{service_id}]"
#             )
#         else:
#             logger.warning(
#                 f"Service ID {service_id} not found in registry for deregistration."
#             )

#     async def aheartbeat(self, service_id: str) -> None:
#         """Update the last heartbeat timestamp for a service instance."""
#         if service_id in self.registry:
#             instance = self.registry[service_id]
#             instance.last_heartbeat = time.time()
#             self.registry[service_id].status = StatusEnum.HEALTHY
#             await self._asave_registry()
#             logger.debug(
#                 f"Heartbeat received for service: '{instance.service_name}' [{service_id}]"
#             )
#         else:
#             logger.warning(
#                 f"Service ID {service_id} not found in registry for heartbeat."
#             )

#     async def aget_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
#         """Get all healthy service instances."""
#         return services  # Mock usage

#     async def ahealth_check_loop(self) -> None:
#         """Periodically check the health of registered services."""
#         while True:
#             await self._acheck_all_health()
#             await asyncio.sleep(self.health_check_interval)

#     async def _acheck_single_health(
#         self, aclient: httpx.AsyncClient, service_id: str
#     ) -> None:
#         """Check health of a registered services and update its status."""
#         instance: ServiceInstance = self.registry[service_id]
#         try:
#             response = await aclient.get(instance.health_check_url)
#             if response.status_code == 200:
#                 instance.status = StatusEnum.HEALTHY
#             else:
#                 instance.status = StatusEnum.UNHEALTHY

#         except Exception as e:
#             logger.warning(
#                 f"Health check failed for service '{instance.service_name}' [{service_id}]: {e}"
#             )
#             instance.status = StatusEnum.UNHEALTHY
#         if instance.is_stale:
#             instance.status = StatusEnum.UNHEALTHY
#             logger.warning(
#                 f"Removing stale service: '{instance.service_name}' [{service_id}]."
#             )
#         await self.aderegister(service_id)

#     async def _acheck_all_health(self) -> None:
#         """Check health of all registered services and update their status."""
#         async with httpx.AsyncClient(timeout=5) as aclient:
#             tasks = [
#                 self._acheck_single_health(aclient, service_id)
#                 for service_id in self.registry.keys()
#             ]

#             # Run health checks concurrently
#             await asyncio.gather(*tasks)

#         # Save updated statuses
#         await self._asave_registry()

#     def list_all_services(self) -> dict[str, list[ServiceInstance]]:
#         """List all registered service instances grouped by service name."""
#         services: dict[str, list[ServiceInstance]] = {}

#         for instance in self.registry.values():
#             # If services not in dict, initialize list
#             if instance.service_name not in services:
#                 services[instance.service_name] = []
#                 # Add instance to the list
#             services[instance.service_name].append(instance)
#         return services


# class SelfRegisteringBackend:
#     """
#     Mock backend that automatically registers itself on startup
#     and sends heartbeats
#     """

#     def __init__(
#         self, model_type: ModelTypeEnum, port: int, registry: ServiceRegistry
#     ) -> None:
#         self.model_type = model_type
#         self.port = port
#         self.registry = registry
#         self.service_id = f"{model_type.value}-{port}-{int(time.time())}"

#     async def register_and_start_heartbeat(self) -> None:
#         """Register service and start heartbeat loop"""
#         # Register this instance
#         instance = ServiceInstance(
#             service_id=self.service_id,
#             service_name=self.model_type.value,
#             host="localhost",  # In production: auto-detect or from env
#             port=self.port,
#             protocol=ProtocolEnum.HTTP,
#             health_check_url=f"http://localhost:{self.port}/health",
#             metadata={"model_type": self.model_type.value, "version": "1.0.0"},
#             registered_at=time.time(),
#             last_heartbeat=time.time(),
#         )

#         await self.registry.aregister(instance)

#         # Start heartbeat loop
#         asyncio.create_task(self._heartbeat_loop())

#     async def _heartbeat_loop(self) -> None:
#         """Send periodic heartbeats to registry"""
#         while True:
#             await asyncio.sleep(10)
#             await self.registry.aheartbeat(self.service_id)
#             print(f"💓 Heartbeat sent: {self.service_id}")

#     async def deregister(self) -> None:
#         """Deregister on shutdown"""
#         await self.registry.aderegister(self.service_id)


# # ============================================================================
# # EXAMPLE USAGE
# # ============================================================================


# async def example_gateway_with_discovery() -> None:
#     """Example: Gateway using service discovery"""

#     # Initialize service registry
#     registry = ServiceRegistry()
#     await registry.ainitialize()

#     # Start health check background task
#     asyncio.create_task(registry.ahealth_check_loop())

#     # Create dynamic backend registry
#     backend_registry = BackendRegistry(registry)

#     # Simulate making requests
#     for i in range(5):
#         try:
#             endpoint = await backend_registry.aget_endpoint(
#                 ModelTypeEnum.CLASSIFICATION
#             )
#             print(f"Request {i + 1} routed to: {endpoint}")
#             await asyncio.sleep(1)
#         except ValueError as e:
#             print(f"Error: {e}")


# async def example_backend_auto_registration() -> None:
#     """Example: Backend that auto-registers"""

#     registry = ServiceRegistry()
#     await registry.ainitialize()

#     # Create and register backend
#     backend = SelfRegisteringBackend(ModelTypeEnum.CLASSIFICATION, 8001, registry)
#     await backend.register_and_start_heartbeat()

#     # Keep running (send heartbeats)
#     await asyncio.sleep(30)

#     # Cleanup on shutdown
#     await backend.deregister()


# if __name__ == "__main__":
#     print("Service Discovery Examples\n")
#     print("Run example_gateway_with_discovery() to see gateway discovering services")
#     print("Run example_backend_auto_registration() to see backend self-registration")

#     # Run gateway example
#     asyncio.run(example_gateway_with_discovery())

# # if __name__ == "__main__":
# # asyncio.run(demo())
