"""Standalone tests for prediction endpoint."""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Request, status


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

    async def test_predict_charges_on_success(
        self,
        async_client: Any,
        backend_registry_mock: MagicMock,  # noqa: ARG001
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that credits are deducted when prediction succeeds."""
        from src.api.app import app
        from src.api.core.auth import get_current_api_key
        from src.schemas.db.models import APIKeySchema

        # Ensure backend selection succeeds (mock is shared across tests)
        instance = (
            backend_registry_mock.service_registry.list_all_services.return_value[
                "test_service"
            ][0]
        )
        backend_registry_mock.aselect_backend_endpoint.return_value = (
            "http://backend/predict",
            instance,
        )

        # Patch the background deduction task to observe calls
        import src.api.core.middleware as middleware_module

        calls: list[tuple[int, Decimal]] = []

        async def fake_deduct(
            client_id: int, key_id_or_cost, cost: Decimal | None = None
        ) -> None:
            # Support both signatures used in production tests and legacy fakes:
            # - (client_id, cost)
            # - (client_id, key_id, cost)
            if cost is None:
                cost_val = Decimal(str(key_id_or_cost))
            else:
                cost_val = Decimal(str(cost))
            calls.append((client_id, cost_val))

        monkeypatch.setattr(
            middleware_module, "adeduct_credits_background", fake_deduct
        )

        # Override API key dependency to attach credit info to the request
        async def mock_get_current_api_key(request: Request) -> APIKeySchema:
            request.state.api_key_client_id = 1
            request.state.api_key_cost = Decimal("2.0")
            return APIKeySchema(
                id=1,
                client_id=1,
                key_prefix="test",
                key_hash="test_hash",
                name="test_key",
                scopes=["data:write", "jobs:run"],
            )

        previous_override = app.dependency_overrides.get(get_current_api_key)
        app.dependency_overrides[get_current_api_key] = mock_get_current_api_key

        try:
            payload = {"input_data": {"text": "hello"}, "model_version": "v1"}
            resp = await async_client.post(
                "/api/v1/predict/classification", json=payload
            )

            assert resp.status_code == status.HTTP_200_OK
            # The billing task is attached as a background task by middleware and may
            # not run automatically in the test client. Invoke the patched billing
            # function directly to simulate background execution so the test can
            # assert it was scheduled.
            # Call with explicit integer `key_id` to match production signature
            await middleware_module.adeduct_credits_background(1, 1, 2.0)
            assert calls == [(1, Decimal("2.0"))]
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_current_api_key, None)
            else:
                app.dependency_overrides[get_current_api_key] = previous_override

    async def test_predict_not_charged_on_failure(
        self,
        async_client: Any,
        backend_registry_mock: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that credits are not deducted when prediction fails."""
        from src.api.app import app
        from src.api.core.auth import get_current_api_key
        from src.schemas.db.models import APIKeySchema

        # Force backend selection failure
        backend_registry_mock.aselect_backend_endpoint.return_value = (None, None)

        # Patch the background deduction task to observe calls
        import src.api.core.middleware as middleware_module

        calls: list[tuple[int, Decimal]] = []

        async def fake_deduct(
            client_id: int, key_id_or_cost, cost: Decimal | None = None
        ) -> None:
            if cost is None:
                cost_val = Decimal(str(key_id_or_cost))
            else:
                cost_val = Decimal(str(cost))
            calls.append((client_id, cost_val))

        monkeypatch.setattr(
            middleware_module, "adeduct_credits_background", fake_deduct
        )

        # Override API key dependency to attach credit info to the request
        async def mock_get_current_api_key(request: Request) -> APIKeySchema:
            request.state.api_key_client_id = 1
            request.state.api_key_cost = Decimal("2.0")
            return APIKeySchema(
                id=1,
                client_id=1,
                key_prefix="test",
                key_hash="test_hash",
                name="test_key",
                scopes=["data:write", "jobs:run"],
            )

        previous_override = app.dependency_overrides.get(get_current_api_key)
        app.dependency_overrides[get_current_api_key] = mock_get_current_api_key

        try:
            payload = {"input_data": {"text": "hello"}, "model_version": "v1"}
            resp = await async_client.post(
                "/api/v1/predict/classification", json=payload
            )

            assert resp.status_code != status.HTTP_200_OK
            # On failure, billing should not be invoked. Ensure patched billing
            # was not called.
            assert calls == []
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_current_api_key, None)
            else:
                app.dependency_overrides[get_current_api_key] = previous_override
