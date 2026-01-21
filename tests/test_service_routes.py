"""Standalone tests for service-related endpoints as a class."""

from typing import Any

import pytest
from fastapi import status


@pytest.mark.asyncio
class TestServiceRoutes:
    """Service endpoint tests grouped in a standalone class."""

    async def test_register_services(self, async_client: Any) -> None:
        """Test registering new service instances."""
        payload = {
            "services": [
                {
                    "service_id": "s1",
                    "service_name": "svc",
                    "host": "localhost",
                    "port": 8001,
                    "protocol": "http",
                    "health_check_url": "http://localhost:8001/health",
                    "metadata": {},
                }
            ]
        }
        resp = await async_client.post("/api/v1/services", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data.get("numRegisteredServices") == len(payload["services"])

    async def test_list_services(self, async_client: Any) -> None:
        """Test listing registered services."""
        resp = await async_client.get("/api/v1/services/list")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "registeredServices" in data
        assert data.get("numRegisteredServices") >= 0

    async def test_deregister_services(self, async_client: Any) -> None:
        """Test deregistering service instances."""
        payload = {"services": ["s1"]}
        resp = await async_client.request("DELETE", "/api/v1/services", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data.get("deregisteredServices") == len(payload["services"])

    async def test_heartbeat(self, async_client: Any) -> None:
        """Test sending heartbeat for a service instance."""
        resp = await async_client.get(
            "/api/v1/services/heartbeat", params={"service_id": "svc-1"}
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "message" in data
