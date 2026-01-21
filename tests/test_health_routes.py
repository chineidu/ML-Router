"""Standalone tests for health endpoint."""

from typing import Any

import pytest
from fastapi import status


@pytest.mark.asyncio
class TestHealthRoutes:
    """Health endpoint tests as a standalone class."""

    async def test_health_check_returns_status_and_backends(
        self, async_client: Any
    ) -> None:
        """Test the health check endpoint."""
        resp = await async_client.get("/api/v1/health")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "status" in data
        assert isinstance(data.get("backends"), dict)
        assert data["backends"].get("test_service") == "1/1 healthy"
