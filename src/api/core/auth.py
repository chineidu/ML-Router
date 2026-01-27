import hashlib
from typing import Any, Callable, Coroutine

from fastapi import Depends, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src import create_logger
from src.api.core.exceptions import HTTPError
from src.config import app_config, app_settings
from src.db.models import aget_db
from src.db.repositories.api_repository import ApiKeyRepository
from src.db.repositories.client_repository import ClientRepository
from src.schemas.db.models import ApiKeySchema, ClientSchema
from src.schemas.types import ClientStatusEnum

logger = create_logger(__name__)
prefix: str = app_config.api_config.prefix
auth_prefix: str = app_config.api_config.auth_prefix

# =========== Configuration ===========
API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)


# =========== API Key Verification ===========
def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Verify a password against its hash."""
    computed_hash = hash_api_key(provided_key)
    return computed_hash == stored_hash


def hash_api_key(provided_keys: str) -> str:
    """Hash a provided keys using the SHA256 algorithm and salt."""
    salt = app_settings.API_KEY_SALT or ""
    return hashlib.sha256((salt + provided_keys).encode()).hexdigest()


# =========== API Key Authentication ===========
def get_api_key_from_header(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Extract API key from header."""
    if not api_key:
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="API key missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return api_key


async def get_current_api_key(
    api_key: str = Depends(get_api_key_from_header), db: AsyncSession = Depends(aget_db)
) -> ApiKeySchema:
    """Dependency to get the current API key."""
    prefix_length = app_settings.API_PREFIX_LENGTH

    if len(api_key) < prefix_length:
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="Invalid API key format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    key_prefix = api_key[:prefix_length]

    api_key_repo = ApiKeyRepository(db)
    db_api_key = await api_key_repo.aget_api_keys_by_prefix(key_prefix=key_prefix)

    if not db_api_key or not verify_api_key(api_key, db_api_key.key_hash):
        logger.warning(f"Unauthorized access attempt with API key prefix: {key_prefix}")
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if the API key is active
    if not db_api_key.active:
        logger.warning(f"Inactive API key used with prefix: {key_prefix}")
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="API key is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if the API key is expired
    if db_api_key.expires_at and db_api_key.expires_at < func.now():
        logger.warning(f"Expired API key used with prefix: {key_prefix}")
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_obj = api_key_repo.convert_DBApiKey_to_schema(db_api_key)
    if not key_obj:
        logger.error(
            f"Failed to convert DBApiKey to ApiKeySchema for prefix: {key_prefix}"
        )
        raise HTTPError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details="Internal server error",
        )
    return key_obj


async def get_current_client(
    api_key: ApiKeySchema = Depends(get_current_api_key),
    db: AsyncSession = Depends(aget_db),
) -> ClientSchema:
    """Dependency to get the current client associated with the API key."""
    client_repo = ClientRepository(db)
    db_client = await client_repo.aget_client_by_id(api_key.client_id)

    if not db_client:
        logger.error(f"Client not found for API key ID: {api_key.id}")
        raise HTTPError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            details="Client not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_obj = client_repo.convert_DBClient_to_schema(db_client)
    if not client_obj:
        logger.error(
            f"Failed to convert DBClient to ClientSchema for client ID: {api_key.client_id}"
        )
        raise HTTPError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details="Internal server error",
        )
    if client_obj.status != ClientStatusEnum.ACTIVE:
        logger.warning(f"Inactive client access attempt: Client ID {client_obj.id}")
        raise HTTPError(
            status_code=status.HTTP_403_FORBIDDEN,
            details=f"Client is {client_obj.status.value.lower()}",
        )
    return client_obj


# =========== Scope-based Authentication ===========


def require_scope(*required_scopes: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Dependency to require specific scopes for an endpoint.

    Parameters
    ----------
    required_scopes : str
        The scopes required to access the endpoint.

    Returns
    -------
    Callable[..., Coroutine[Any, Any, None]]
        A dependency function that checks for the required scopes.

    Usage
    -----
        @router.get("/some-endpoint")
        async def some_endpoint(
            api_key: ApiKeySchema = Depends(require_scope("read:data"))
        ):
            ...

        # Multiple scopes
        @router.post("/another-endpoint")
        async def another_endpoint(
            api_key: ApiKeySchema = Depends(require_scope("write:data", "admin"))
        ):
            ...
    """

    async def _arequire_scope(
        api_key: ApiKeySchema = Depends(get_current_api_key),
    ) -> None:
        if not all(scope in api_key.scopes for scope in required_scopes):
            logger.warning(
                f"API key ID {api_key.id} missing required scopes: {required_scopes}"
            )
            raise HTTPError(
                status_code=status.HTTP_403_FORBIDDEN,
                details=f"Insufficient permissions. Needs scopes: {', '.join(required_scopes)}",
            )

    return _arequire_scope


def require_any_scope(
    *required_scopes: str,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Dependency to require any scope for an endpoint.

    Parameters
    ----------
    required_scopes : str
        The scopes required to access the endpoint.

    Returns
    -------
    Callable[..., Coroutine[Any, Any, None]]
        A dependency function that checks for the required scopes.

    Usage
    -----

        # Multiple scopes
        @router.post("/another-endpoint")
        async def another_endpoint(
            api_key: ApiKeySchema = Depends(require_any_scope("read:data", "admin"))
        ):
            ...
    """

    async def _arequire_any_scope(
        api_key: ApiKeySchema = Depends(get_current_api_key),
    ) -> None:
        if not any(scope in api_key.scopes for scope in required_scopes):
            logger.warning(
                f"API key ID {api_key.id} has insufficient required scopes: {required_scopes}"
            )
            raise HTTPError(
                status_code=status.HTTP_403_FORBIDDEN,
                details=f"Insufficient permissions. Needs one of {', '.join(required_scopes)}",
            )

    return _arequire_any_scope
