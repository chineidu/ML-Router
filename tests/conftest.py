from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.core.dependencies import (
    get_backend_registry,
    get_cache,
    get_client,
    get_service_registry,
)
from src.schemas.backend_registry import ServiceInstance
from src.schemas.types import ProtocolEnum, StatusEnum


@pytest.fixture(scope="module")
def backend_registry_mock() -> MagicMock:
    """Create a mock BackendRegistry with the methods used by routes."""
    backend_registry = MagicMock()

    # service_registry used by health route
    service_registry = MagicMock()

    # Default: one service with one healthy ServiceInstance
    instance = ServiceInstance(
        service_id="svc-1",
        service_name="test_service",
        host="localhost",
        port=8000,
        protocol=ProtocolEnum.HTTP,
        ttl_seconds=30,
        health_check_url="http://localhost:8000/health",
        metadata={},
        last_heartbeat=None,
        status=StatusEnum.HEALTHY,
    )
    service_registry.list_all_services.return_value = {"test_service": [instance]}

    # Async methods used by predict route
    backend_registry.aselect_backend_endpoint = AsyncMock(
        return_value=("http://backend/predict", instance)
    )
    backend_registry.aupdate_active_connection = AsyncMock()
    backend_registry.service_registry = service_registry
    backend_registry.service_registry.asave_registry = AsyncMock()
    backend_registry.service_registry.compute_dynamic_weight = MagicMock(return_value=1)

    return backend_registry


@pytest.fixture(scope="module")
def service_registry_mock() -> MagicMock:
    """Create a mock ServiceRegistry with the async methods used by service routes."""
    service_registry = MagicMock()
    service_registry.abatch_register = AsyncMock(return_value=True)
    svc_instance = ServiceInstance(
        service_id="s1",
        service_name="svc",
        host="localhost",
        port=8001,
        protocol=ProtocolEnum.HTTP,
        ttl_seconds=30,
        health_check_url="http://localhost:8001/health",
        metadata={},
        last_heartbeat=None,
        status=StatusEnum.HEALTHY,
    )
    service_registry.list_all_services = MagicMock(return_value={"svc": [svc_instance]})
    service_registry.abatch_deregister = AsyncMock(return_value=True)
    service_registry.aheartbeat = AsyncMock(return_value=True)
    return service_registry


@pytest.fixture(scope="module")
def httpx_client_mock() -> AsyncMock:
    """Mock for an async HTTP client used by the predict route."""
    client = AsyncMock()

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"modelVersion": "v1", "prediction": {"score": 0.9}}

    client.post = AsyncMock(return_value=response)
    return client


@pytest.fixture(scope="module")
def client(
    backend_registry_mock: MagicMock,
    service_registry_mock: MagicMock,
    httpx_client_mock: AsyncMock,
) -> Generator[TestClient, None, None]:
    """TestClient configured with mocked app state resources."""
    from src.api.app import app

    # Ensure FastAPI dependencies use our mocks (lifespan may overwrite app.state)
    app.dependency_overrides[get_backend_registry] = lambda: backend_registry_mock
    app.dependency_overrides[get_service_registry] = lambda: service_registry_mock
    app.dependency_overrides[get_client] = lambda: httpx_client_mock

    # Provide async cache methods expected by the cached decorator
    class AsyncCacheMock:
        async def get(self, key) -> None:  # noqa: ANN001, ARG002
            return None

        async def set(self, key, value, ttl=None) -> None:  # noqa: ANN001
            pass

    async_cache = AsyncCacheMock()
    app.dependency_overrides[get_cache] = lambda: async_cache

    with TestClient(app) as tc:
        # After startup, double-check state (keep for compatibility)
        app.state.backend_registry = backend_registry_mock
        app.state.service_registry = service_registry_mock
        app.state.client = httpx_client_mock
        app.state.cache = async_cache
        yield tc


@pytest.fixture(scope="function")
async def async_client(
    backend_registry_mock: MagicMock,
    service_registry_mock: MagicMock,
    httpx_client_mock: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client configured with mocked app state resources."""
    from src.api.app import app

    # Override dependencies so endpoints use mocks regardless of startup
    app.dependency_overrides[get_backend_registry] = lambda: backend_registry_mock
    app.dependency_overrides[get_service_registry] = lambda: service_registry_mock
    app.dependency_overrides[get_client] = lambda: httpx_client_mock

    # Provide async cache methods expected by the cached decorator
    class AsyncCacheMock:
        async def get(self, key) -> None:  # noqa: ANN001, ARG002
            return None

        async def set(self, key, value, ttl=None) -> None:  # noqa: ANN001
            pass

    async_cache = AsyncCacheMock()
    app.dependency_overrides[get_cache] = lambda: async_cache

    # httpx versions differ in how ASGI apps are provided. Try the simplest API first,
    # otherwise fall back to using an ASGI transport.
    try:
        ac = AsyncClient(app=app, base_url="http://testserver")  # type: ignore[arg-type]
    except TypeError:
        try:
            from httpx import ASGITransport

            transport = ASGITransport(app=app)
        except Exception:
            from httpx._transports.asgi import ASGITransport  # type: ignore

            transport = ASGITransport(app=app)  # type: ignore[arg-type]

        ac = AsyncClient(transport=transport, base_url="http://testserver")

    async with ac as client:
        # Ensure app.state has mocks after startup (lifespan may have overwritten)
        app.state.backend_registry = backend_registry_mock
        app.state.service_registry = service_registry_mock
        app.state.client = httpx_client_mock
        app.state.cache = async_cache  # Override the cache set by lifespan
        yield client
