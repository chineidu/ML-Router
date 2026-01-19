"""
Auto-discovers running Docker Compose services using the Docker API.
"""

import asyncio
import re
from typing import Any

from docker.models.containers import Container

import docker
from src.schemas.backend_registry import ServiceInstance
from src.schemas.types import ModelTypeEnum, ProtocolEnum, StatusEnum


class DockerServiceDiscovery:
    """
    Discovers ML model services from Docker containers.

    Automatically detects services running in Docker Compose by:
        1. Scanning running containers
        2. Parsing command arguments to extract model type and port
        3. Creating ServiceInstance objects for integration with ServiceRegistry

    Notes
    -----
    This class is intended for dynamic service discovery in environments using Docker Compose.
    """

    def __init__(self, compose_project_name: str | None = None) -> None:
        """
        Initialize Docker service discovery.

        Parameters
        ----------
        compose_project_name : str or None, optional
            Filter containers by Docker Compose project name. If None, discovers all containers.
        """
        self.client = docker.from_env()
        self.compose_project_name = compose_project_name

    def discover_model_services(self) -> dict[str, ServiceInstance]:
        """
        Discover all ML model services running in Docker.

        Returns
        -------
        dict[str, ServiceInstance]
            Dictionary mapping service_id to ServiceInstance. Only includes containers running model services.
        """
        containers: list[Container] = self.client.containers.list()
        services: dict[str, ServiceInstance] = {}

        for container in containers:
            labels = container.labels

            # Filter by compose project if specified
            if self.compose_project_name:
                if (
                    labels.get("com.docker.compose.project")
                    != self.compose_project_name
                ):
                    continue

            # Parse service instance from container
            service_instance = self._parse_container_to_service(container)
            if service_instance:
                services[service_instance.service_id] = service_instance

        return services

    async def adiscover_model_services(self) -> dict[str, ServiceInstance]:
        """
        Asynchronously discover all ML model services running in Docker.

        Returns
        -------
        dict[str, ServiceInstance]
            Dictionary mapping service_id to ServiceInstance. Only includes containers running model services.
        """
        return await asyncio.to_thread(self.discover_model_services)

    def _parse_container_to_service(
        self, container: Container
    ) -> ServiceInstance | None:
        """
        Parse a Docker container into a ServiceInstance.

        Parameters
        ----------
        container : Container
            Docker container object.

        Returns
        -------
        ServiceInstance or None
            ServiceInstance if container is a model service, None otherwise.
        """
        labels = container.labels
        attrs = container.attrs

        # Get container command to parse model type and port
        command = attrs.get("Config", {}).get("Cmd", [])
        command_str = " ".join(command) if command else ""

        # Skip non-model services (database, redis, api_gateway, etc.)
        service_name = labels.get("com.docker.compose.service", container.name)
        if not self._is_model_service(service_name, command_str):
            return None

        # Extract model type from command (e.g., --model sentiment)
        model_type = self._extract_model_type(command_str)
        if not model_type:
            return None

        # Extract port from command (e.g., --port 8001)
        container_port = self._extract_port(command_str)
        if not container_port:
            return None

        # Determine host - use container name for Docker networks, localhost for host access
        # In Docker Compose, containers can communicate using service names
        host = service_name  # Use the compose service name for inter-container communication

        # Get container ID safely
        container_id = container.id[:12] if container.id else "unknown"

        # Create ServiceInstance
        return ServiceInstance(
            service_id=f"{model_type}-{service_name}-{container_id}",
            service_name=model_type,  # Use model type as service name (e.g., "sentiment")
            host=host,
            port=container_port,  # Use container port for inter-container communication
            protocol=ProtocolEnum.HTTP,
            ttl_seconds=30,
            health_check_url=f"http://{host}:{container_port}/health",
            metadata={
                "container_id": container.id,
                "container_name": container.name,
                "compose_service": service_name,
                "image": (
                    getattr(container.image, "tags", ["unknown"])[0]
                    if getattr(container.image, "tags", None)
                    else "unknown"
                ),
            },
            status=StatusEnum.HEALTHY
            if container.status == "running"
            else StatusEnum.UNHEALTHY,
        )

    def _is_model_service(self, service_name: str, command: str) -> bool:
        """
        Check if the service is a model service based on name and command.

        Parameters
        ----------
        service_name : str
            Name of the Docker Compose service.
        command : str
            Command string used to start the container.

        Returns
        -------
        bool
            True if the service is a model service, False otherwise.
        """
        # Services running src.mock.app are model services
        return "src.mock.app" in command or any(
            keyword in service_name.lower()
            for keyword in [typ.value for typ in ModelTypeEnum]
        )

    def _extract_model_type(self, command: str) -> str | None:
        """
        Extract model type from command string.

        Parameters
        ----------
        command : str
            Command string used to start the container.

        Returns
        -------
        str or None
            Model type string if found and valid, otherwise None.

        Examples
        --------
        'python -m src.mock.app --model sentiment --port 8001' -> 'sentiment'
        """
        match = re.search(r"--model\s+(\w+)", command)
        if match:
            model_str = match.group(1)
            # Validate it's a known model type
            try:
                ModelTypeEnum(model_str)
                return model_str
            except ValueError:
                return None
        return None

    def _extract_port(self, command: str) -> int | None:
        """
        Extract port number from command string.

        Parameters
        ----------
        command : str
            Command string used to start the container.

        Returns
        -------
        int or None
            Port number if found, otherwise None.

        Examples
        --------
        'python -m src.mock.app --model sentiment --port 8001' -> 8001
        """
        match = re.search(r"--port\s+(\d+)", command)
        if match:
            return int(match.group(1))
        return None

    def _get_host_port(self, container: Any, container_port: int) -> int | None:
        """
        Get the host port mapped to the container port.

        Parameters
        ----------
        container : Any
            Docker container object.
        container_port : int
            Port inside the container.

        Returns
        -------
        int or None
            Host port number if mapped, otherwise None.
        """
        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})

        # Docker API returns ports like: {"8001/tcp": [{"HostPort": "8001"}]}
        port_key = f"{container_port}/tcp"
        if port_key in ports and ports[port_key]:
            host_port_str = ports[port_key][0].get("HostPort")
            if host_port_str:
                return int(host_port_str)

        return None

    def get_service_count(self) -> int:
        """
        Get count of discovered model services.

        Returns
        -------
        int
            Number of discovered model services.
        """
        return len(self.discover_model_services())

    async def aget_service_count(self) -> int:
        """
        Asynchronously get count of discovered model services.

        Returns
        -------
        int
            Number of discovered model services.
        """
        services = await self.adiscover_model_services()
        return len(services)


if __name__ == "__main__":
    import json
    import os

    # Optionally set the compose project name from env or arg
    project = os.environ.get("COMPOSE_PROJECT_NAME", "ml-router")

    dsd = DockerServiceDiscovery(compose_project_name=project)
    services = dsd.discover_model_services()

    print(f"Discovered {len(services)} model services:\n")

    for service_id, instance in services.items():
        print(f"Service ID: {service_id}")
        print(f"  Name: {instance.service_name}")
        print(f"  Endpoint: {instance.endpoint_url}/predict")
        print(f"  Health Check: {instance.health_check_url}")
        print(f"  Status: {instance.status.value}")
        print(f"  Metadata: {json.dumps(instance.metadata, indent=4)}")
        print()
