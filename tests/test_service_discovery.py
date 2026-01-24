"""Tests for service discovery components."""

import json
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.core.exceptions import ServiceUnavailableError
from src.schemas.backend_registry import ServiceInstance
from src.schemas.types import (
    LoadBalancerStrategyEnum,
    ModelTypeEnum,
    ProtocolEnum,
    StatusEnum,
)
from src.services.docker_service_discovery import DockerServiceDiscovery
from src.services.service_discovery import BackendRegistry, ServiceRegistry


class TestServiceRegistry:
    """Test cases for ServiceRegistry class."""

    @pytest.fixture
    def temp_registry_file(self) -> Generator[str, None, None]:
        """Create a temporary registry file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            sample_data = {
                "svc-1": {
                    "service_id": "svc-1",
                    "service_name": "sentiment",
                    "host": "localhost",
                    "port": 8001,
                    "protocol": "http",
                    "ttl_seconds": 30,
                    "health_check_url": "http://localhost:8001/health",
                    "metadata": {"container_id": "abc123"},
                    "last_heartbeat": None,
                    "status": "healthy",
                }
            }
            json.dump(sample_data, f)
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def service_registry(self, temp_registry_file: str) -> ServiceRegistry:
        """Create a ServiceRegistry instance for testing."""
        registry = ServiceRegistry(
            registry_file=temp_registry_file,
            load_registry_from_file=True,
            health_check_interval=10,
        )
        # Skip real HTTP health checks
        registry._acheck_all_health = AsyncMock(return_value=None)
        return registry

    @pytest.mark.asyncio
    async def test_ainitialize_loads_from_file(
        self, service_registry: ServiceRegistry
    ) -> None:
        """Test that ainitialize loads registry from file."""
        await service_registry.ainitialize()
        assert len(service_registry.registry) == 1
        assert "svc-1" in service_registry.registry
        instance = service_registry.registry["svc-1"]
        assert instance.service_name == "sentiment"
        assert instance.port == 8001

    @pytest.mark.asyncio
    async def test_aregister_new_service(
        self, service_registry: ServiceRegistry
    ) -> None:
        """Test registering a new service instance."""
        await service_registry.ainitialize()
        new_instance = ServiceInstance(
            service_id="svc-2",
            service_name="classification",
            host="localhost",
            port=8002,
            protocol=ProtocolEnum.HTTP,
            ttl_seconds=30,
            health_check_url="http://localhost:8002/health",
            metadata={},
        )
        result = await service_registry.aregister(new_instance)
        assert result is True
        assert "svc-2" in service_registry.registry

    @pytest.mark.asyncio
    async def test_aderegister_existing_service(
        self, service_registry: ServiceRegistry
    ) -> None:
        """Test deregistering an existing service."""
        await service_registry.ainitialize()
        result = await service_registry.aderegister("svc-1")
        assert result is True
        assert "svc-1" not in service_registry.registry

    @pytest.mark.asyncio
    async def test_aderegister_nonexistent_service(
        self, service_registry: ServiceRegistry
    ) -> None:
        """Test deregistering a service that doesn't exist."""
        await service_registry.ainitialize()
        result = await service_registry.aderegister("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_aheartbeat_updates_timestamp(
        self, service_registry: ServiceRegistry
    ) -> None:
        """Test that heartbeat updates the last_heartbeat timestamp."""
        await service_registry.ainitialize()
        result = await service_registry.aheartbeat("svc-1")
        assert result is True
        instance = service_registry.registry["svc-1"]
        assert instance.status == StatusEnum.HEALTHY

    def test_list_all_services(self, service_registry: ServiceRegistry) -> None:
        """Test listing all services grouped by name."""
        service_registry.registry = {
            "svc-1": ServiceInstance(
                service_id="svc-1",
                service_name="sentiment",
                host="localhost",
                port=8001,
                protocol=ProtocolEnum.HTTP,
                ttl_seconds=30,
                health_check_url="http://localhost:8001/health",
                metadata={},
            ),
            "svc-2": ServiceInstance(
                service_id="svc-2",
                service_name="sentiment",
                host="localhost",
                port=8002,
                protocol=ProtocolEnum.HTTP,
                ttl_seconds=30,
                health_check_url="http://localhost:8002/health",
                metadata={},
            ),
            "svc-3": ServiceInstance(
                service_id="svc-3",
                service_name="classification",
                host="localhost",
                port=8003,
                protocol=ProtocolEnum.HTTP,
                ttl_seconds=30,
                health_check_url="http://localhost:8003/health",
                metadata={},
            ),
        }
        services = service_registry.list_all_services()
        assert len(services) == 2
        assert len(services["sentiment"]) == 2
        assert len(services["classification"]) == 1

    def test_compute_dynamic_weight_healthy(self) -> None:
        """Test dynamic weight computation for healthy service."""
        instance = ServiceInstance(
            service_id="test",
            service_name="sentiment",
            host="localhost",
            port=8001,
            protocol=ProtocolEnum.HTTP,
            ttl_seconds=30,
            health_check_url="http://localhost:8001/health",
            metadata={"base_weight": 100},
            status=StatusEnum.HEALTHY,
        )
        instance.runtime_metrics.active_connections = 10
        weight = ServiceRegistry.compute_dynamic_weight(instance)
        assert 1 <= weight <= 100

    def test_compute_dynamic_weight_unhealthy(self) -> None:
        """Test dynamic weight computation for unhealthy service."""
        instance = ServiceInstance(
            service_id="test",
            service_name="sentiment",
            host="localhost",
            port=8001,
            protocol=ProtocolEnum.HTTP,
            ttl_seconds=30,
            health_check_url="http://localhost:8001/health",
            metadata={},
            status=StatusEnum.UNHEALTHY,
        )
        weight = ServiceRegistry.compute_dynamic_weight(instance)
        assert weight == 0


class TestBackendRegistry:
    """Test cases for BackendRegistry class."""

    @pytest.fixture
    def service_registry_mock(self) -> MagicMock:
        """Create a mock ServiceRegistry for BackendRegistry testing."""
        registry = MagicMock()
        instances = [
            ServiceInstance(
                service_id=f"sentiment-{i}",
                service_name="sentiment",
                host="localhost",
                port=8000 + i,
                protocol=ProtocolEnum.HTTP,
                ttl_seconds=30,
                health_check_url=f"http://localhost:{8000 + i}/health",
                metadata={},
                status=StatusEnum.HEALTHY,
            )
            for i in range(3)
        ]
        for i, instance in enumerate(instances):
            instance.runtime_metrics.active_connections = i * 10
            instance.runtime_metrics.weight = 100 - i * 10

        registry.aget_healthy_instances = AsyncMock(return_value=instances)
        registry.aget_healthy_instances_cached = AsyncMock(return_value=instances)
        registry.get_healthy_instances_cached = MagicMock(return_value=instances)
        registry.compute_dynamic_weight = MagicMock(return_value=50)
        return registry

    @pytest.fixture
    def backend_registry(self, service_registry_mock: MagicMock) -> BackendRegistry:
        """Create a BackendRegistry instance for testing."""
        return BackendRegistry(service_registry_mock)

    @pytest.mark.asyncio
    async def test_aselect_backend_endpoint(
        self, backend_registry: BackendRegistry
    ) -> None:
        """Test selecting backend endpoint."""
        endpoint, instance = await backend_registry.aselect_backend_endpoint(
            ModelTypeEnum.SENTIMENT, LoadBalancerStrategyEnum.ROUND_ROBIN
        )
        assert endpoint is not None
        assert "predict" in endpoint
        assert instance is not None
        assert instance.service_name == "sentiment"

    @pytest.mark.asyncio
    async def test_aget_all_instances(self, backend_registry: BackendRegistry) -> None:
        """Test getting all instances for a model type."""
        instances = await backend_registry.aget_all_instances(ModelTypeEnum.SENTIMENT)
        assert len(instances) == 3
        assert all(inst.service_name == "sentiment" for inst in instances)

    @pytest.mark.asyncio
    async def test_around_robin_strategy(
        self, backend_registry: BackendRegistry
    ) -> None:
        """Test round-robin load balancing strategy."""
        inst1 = await backend_registry._around_robin_strategy(ModelTypeEnum.SENTIMENT)
        inst2 = await backend_registry._around_robin_strategy(ModelTypeEnum.SENTIMENT)
        inst3 = await backend_registry._around_robin_strategy(ModelTypeEnum.SENTIMENT)
        inst4 = await backend_registry._around_robin_strategy(ModelTypeEnum.SENTIMENT)

        assert inst1.service_id == "sentiment-0"
        assert inst2.service_id == "sentiment-1"
        assert inst3.service_id == "sentiment-2"
        assert inst4.service_id == "sentiment-0"

    @pytest.mark.asyncio
    async def test_aleast_connections_strategy(
        self, backend_registry: BackendRegistry
    ) -> None:
        """Test least connections load balancing strategy."""
        instance = await backend_registry._aleast_connections_strategy(
            ModelTypeEnum.SENTIMENT
        )
        assert instance.service_id == "sentiment-0"

    @pytest.mark.asyncio
    async def test_aweighted_strategy(self, backend_registry: BackendRegistry) -> None:
        """Test weighted load balancing strategy."""
        instance = await backend_registry._aweighted_strategy(ModelTypeEnum.SENTIMENT)
        assert instance.service_name == "sentiment"

    @pytest.mark.asyncio
    async def test_aselect_load_balancer_invalid_strategy(
        self, backend_registry: BackendRegistry
    ) -> None:
        """Test selecting load balancer with invalid strategy."""
        with pytest.raises(ValueError, match="Invalid load balancing strategy"):
            await backend_registry.aselect_load_balancer(
                ModelTypeEnum.SENTIMENT,
                "invalid_strategy",  # type: ignore
            )

    @pytest.mark.asyncio
    async def test_around_robin_no_healthy_instances(
        self, backend_registry: BackendRegistry, service_registry_mock: MagicMock
    ) -> None:
        """Test round-robin strategy when no healthy instances available."""
        service_registry_mock.aget_healthy_instances = AsyncMock(return_value=[])
        service_registry_mock.aget_healthy_instances_cached = AsyncMock(return_value=[])
        with pytest.raises(ServiceUnavailableError):
            await backend_registry._around_robin_strategy(ModelTypeEnum.SENTIMENT)


class TestDockerServiceDiscovery:
    """Test cases for DockerServiceDiscovery class."""

    @pytest.fixture
    def docker_client_mock(self) -> MagicMock:
        """Create a mock Docker client."""
        client = MagicMock()
        container = MagicMock()
        container.id = "abc123def456"
        container.name = "sentiment-service-1"
        container.status = "running"
        container.labels = {
            "com.docker.compose.service": "sentiment-service",
            "com.docker.compose.project": "ml-router",
        }
        container.image.tags = ["sentiment-model:latest"]
        container.attrs = {
            "Config": {
                "Cmd": [
                    "python",
                    "-m",
                    "src.mock.app",
                    "--model",
                    "sentiment",
                    "--port",
                    "8001",
                ]
            },
            "NetworkSettings": {"Ports": {"8001/tcp": [{"HostPort": "8001"}]}},
        }
        client.containers.list.return_value = [container]
        return client

    @pytest.fixture
    def docker_discovery(self, docker_client_mock: MagicMock) -> DockerServiceDiscovery:
        """Create a DockerServiceDiscovery instance."""
        with patch("docker.from_env", return_value=docker_client_mock):
            return DockerServiceDiscovery(compose_project_name="ml-router")

    def test_discover_model_services(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test discovering model services from Docker."""
        services = docker_discovery.discover_model_services()
        assert len(services) == 1
        service_id = list(services.keys())[0]
        instance = services[service_id]
        assert instance.service_name == "sentiment"
        assert instance.host == "sentiment-service"
        assert instance.port == 8001
        assert instance.protocol == ProtocolEnum.HTTP
        assert instance.status == StatusEnum.HEALTHY

    def test_discover_model_services_wrong_project(
        self, docker_client_mock: MagicMock
    ) -> None:
        """Test that services from wrong project are filtered out."""
        docker_client_mock.containers.list.return_value[0].labels[
            "com.docker.compose.project"
        ] = "other-project"
        with patch("docker.from_env", return_value=docker_client_mock):
            discovery = DockerServiceDiscovery(compose_project_name="ml-router")
            services = discovery.discover_model_services()
        assert len(services) == 0

    def test_parse_container_to_service_valid(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test parsing a valid container to service instance."""
        container = MagicMock()
        container.id = "test123"
        container.name = "test-service"
        container.status = "running"
        container.labels = {"com.docker.compose.service": "test-service"}
        container.image.tags = ["test:latest"]
        container.attrs = {
            "Config": {
                "Cmd": [
                    "python",
                    "-m",
                    "src.mock.app",
                    "--model",
                    "sentiment",
                    "--port",
                    "8001",
                ]
            }
        }
        instance = docker_discovery._parse_container_to_service(container)
        assert instance is not None
        assert instance.service_name == "sentiment"
        assert instance.port == 8001

    def test_parse_container_to_service_not_model_service(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test parsing a container that is not a model service."""
        container = MagicMock()
        container.attrs = {"Config": {"Cmd": ["redis-server"]}}
        instance = docker_discovery._parse_container_to_service(container)
        assert instance is None

    def test_extract_model_type(self, docker_discovery: DockerServiceDiscovery) -> None:
        """Test extracting model type from command."""
        assert (
            docker_discovery._extract_model_type("--model sentiment --port 8001")
            == "sentiment"
        )
        assert docker_discovery._extract_model_type("--model invalid") is None

    def test_extract_port(self, docker_discovery: DockerServiceDiscovery) -> None:
        """Test extracting port from command."""
        assert docker_discovery._extract_port("--port 8001 --model sentiment") == 8001
        assert docker_discovery._extract_port("no port flag") is None

    def test_get_host_port(self, docker_discovery: DockerServiceDiscovery) -> None:
        """Test getting host port mapping."""
        container = MagicMock()
        container.attrs = {
            "NetworkSettings": {"Ports": {"8001/tcp": [{"HostPort": "8001"}]}}
        }
        host_port = docker_discovery._get_host_port(container, 8001)
        assert host_port == 8001

    def test_get_host_port_no_mapping(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test getting host port when no mapping exists."""
        container = MagicMock()
        container.attrs = {"NetworkSettings": {"Ports": {}}}
        host_port = docker_discovery._get_host_port(container, 8001)
        assert host_port is None

    @pytest.mark.asyncio
    async def test_adiscover_model_services(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test async discovery of model services."""
        services = await docker_discovery.adiscover_model_services()
        assert len(services) == 1
        assert isinstance(services, dict)

    def test_get_service_count(self, docker_discovery: DockerServiceDiscovery) -> None:
        """Test getting service count."""
        count = docker_discovery.get_service_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_aget_service_count(
        self, docker_discovery: DockerServiceDiscovery
    ) -> None:
        """Test async getting service count."""
        count = await docker_discovery.aget_service_count()
        assert count == 1
