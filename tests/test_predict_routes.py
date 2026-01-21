"""Standalone tests for prediction endpoint."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import status


@pytest.mark.asyncio
class TestClientPredictRoutes:
    """Tests for prediction routes."""

    async def test_predict_success(
        self,
        async_client: Any,
        backend_registry_mock: MagicMock,  # noqa: ARG001, ARG002
    ) -> None:
        """Test successful prediction request."""
        payload = {"input_data": {"text": "hello"}, "model_version": "v1"}
        resp = await async_client.post("/api/v1/predict/classification", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "prediction" in data

    async def test_predict_no_backend(
        self, async_client: Any, backend_registry_mock: MagicMock
    ) -> None:
        """Test prediction request when no backend is available."""
        backend_registry_mock.aselect_backend_endpoint.return_value = (None, None)
        payload = {"input_data": {"text": "hello"}, "model_version": "v1"}
        resp = await async_client.post("/api/v1/predict/classification", json=payload)
        assert resp.status_code != status.HTTP_200_OK
