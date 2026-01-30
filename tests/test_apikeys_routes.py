"""Tests for API key routes."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import status


@pytest.mark.asyncio
class TestAPIKeyRoutes:
    async def test_register_apikey(self, async_client: Any, monkeypatch) -> None:
        """Test registering a new API key."""

        # Fake repository
        class FakeRepo:
            def __init__(self, db=None):
                pass

            async def acreate_api_key(self, api_key_obj):
                return 123

        import src.api.routes.v1.apikeys as apikeys_module
        from src.api.app import app
        from src.api.core.auth import get_current_active_user

        monkeypatch.setattr(apikeys_module, "APIKeyRepository", FakeRepo)
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=1, external_id="test-owner", tier="free"
        )

        payload = {"name": "test-key", "scopes": ["data:read"], "expires_at": None}
        resp = await async_client.post("/api/v1/auth/apikeys", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "fullKey" in data
        assert data["name"] == "test-key"
        assert data["id"] == 123

    async def test_list_apikeys(self, async_client: Any, monkeypatch) -> None:
        """Test listing API keys for the authenticated user."""
        now = datetime.now(timezone.utc)

        class FakeKey(SimpleNamespace):
            pass

        key = FakeKey(
            id=1,
            key_prefix="TEST",
            key_hash="hash",
            name="test",
            scopes=["data:read"],
            expires_at=None,
            created_at=now,
        )

        class FakeRepo:
            def __init__(self, db=None):
                pass

            async def aget_keys_by_owner(self, owner_id: int):
                return [key]

        import src.api.routes.v1.apikeys as apikeys_module
        from src.api.app import app
        from src.api.core.auth import get_current_active_user

        monkeypatch.setattr(apikeys_module, "APIKeyRepository", FakeRepo)
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=1, external_id="test-owner", tier="free"
        )

        resp = await async_client.get("/api/v1/auth/apikeys")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "success"
        api_keys = data.get("apiKeys") or data.get("api_keys")
        assert isinstance(api_keys, list)
        assert api_keys[0]["name"] == "test"

    async def test_update_apikey(self, async_client: Any, monkeypatch) -> None:
        """Test updating an existing API key."""
        now = datetime.now(timezone.utc)

        class FakeKey(SimpleNamespace):
            pass

        updated = FakeKey(
            id=1,
            key_prefix="TEST",
            key_hash="hash",
            name="updated",
            scopes=["data:read"],
            expires_at=None,
            created_at=now,
        )

        class FakeRepo:
            def __init__(self, db=None):
                pass

            async def aupdate_api_key(
                self, key_id: int, client_id: int, update_data: dict
            ):
                return updated

        import src.api.routes.v1.apikeys as apikeys_module
        from src.api.app import app
        from src.api.core.auth import get_current_active_user

        monkeypatch.setattr(apikeys_module, "APIKeyRepository", FakeRepo)
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=1, external_id="test-owner", tier="free"
        )

        payload = {"id": 1, "name": "updated"}
        resp = await async_client.patch("/api/v1/auth/apikeys", json=payload)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["name"] == "updated"
        assert data["id"] == 1

    async def test_deregister_apikey(self, async_client: Any, monkeypatch) -> None:
        """Test deregistering an API key."""

        class FakeRepo:
            def __init__(self, db=None):
                pass

            async def adelete_owned_key(self, key_id: int, owner_id: int):
                return True

        import src.api.routes.v1.apikeys as apikeys_module
        from src.api.app import app
        from src.api.core.auth import get_current_active_user

        monkeypatch.setattr(apikeys_module, "APIKeyRepository", FakeRepo)
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=1, external_id="test-owner", tier="free"
        )

        resp = await async_client.delete("/api/v1/auth/apikeys/1")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "API key deregistered successfully."
