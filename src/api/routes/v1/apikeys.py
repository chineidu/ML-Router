"""API Key Routes."""

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from src import create_logger
from src.api.core.auth import generate_api_key, get_current_active_user, hash_api_key
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import get_rate_limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.db.models import aget_db
from src.db.repositories.api_repository import APIKeyRepository
from src.schemas.db.models import APIKeySchema, APIUpdateSchema, ClientSchema
from src.schemas.routes.apikeys import APICreationSchema, APIResponseSchema
from src.utilities.utils import extract_rate_limit_number

if TYPE_CHECKING:
    pass
logger = create_logger(name=__name__)


router = APIRouter(tags=["apikeys"], default_response_class=MsgSpecJSONResponse)


@router.post("/apikeys", status_code=status.HTTP_200_OK)
async def register_apikey(
    input_data: APICreationSchema,
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
    client: ClientSchema = Depends(get_current_active_user),
) -> APIResponseSchema:
    """Route for registering API keys"""
    api_key_repo = APIKeyRepository(db=db)

    if not api_key_repo:
        raise HTTPError(details="API key repository is not available.")

    prefix, full_key = generate_api_key()
    apikey_hash: str = hash_api_key(full_key)
    limit = extract_rate_limit_number(client.tier)

    api_key_obj = APIKeySchema(
        client_id=str(client.id),
        key_prefix=prefix,
        key_hash=apikey_hash,
        name=input_data.name,
        scopes=input_data.scopes,
        requests_per_minute=limit,
        expires_at=input_data.expires_at,
    )
    if not api_key_obj:
        raise HTTPError(
            status_code=status.HTTP_400_BAD_REQUEST,
            details="Failed to create API key object.",
        )

    # Persist
    api_key_id: int = await api_key_repo.acreate_api_key(api_key_obj=api_key_obj)

    return APIResponseSchema(
        id=api_key_id,
        prefix=prefix,
        name=input_data.name,
        full_key=full_key,
        owner=client.external_id,
        created_at=api_key_obj.created_at,
        updated_at=datetime.now(),
        expires_at=input_data.expires_at,
        scopes=input_data.scopes,
    )


@router.get("/apikeys", status_code=status.HTTP_200_OK)
async def list_apikeys(
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
    client: ClientSchema = Depends(get_current_active_user),
) -> dict[str, str | list[APIResponseSchema]]:
    """Route for listing API keys belonging to the authenticated user."""
    api_key_repo = APIKeyRepository(db=db)

    if not api_key_repo:
        raise HTTPError(details="API key repository is not available.")

    db_api_keys = await api_key_repo.aget_keys_by_owner(
        owner_id=int(client.id) if client.id else 0
    )
    api_keys = [
        APIResponseSchema(
            id=key.id,
            prefix=key.key_prefix,
            full_key=f"{key.key_prefix}...",  # Don't return full key!
            name=key.name,
            owner=client.external_id,
            scopes=key.scopes,
            expires_at=key.expires_at,
            created_at=key.created_at,
        )
        for key in db_api_keys
    ]
    return {"status": "success", "api_keys": api_keys}


@router.patch("/apikeys", status_code=status.HTTP_200_OK)
async def update_apikey(
    input_data: APIUpdateSchema,
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
    client: ClientSchema = Depends(get_current_active_user),
) -> APIResponseSchema:
    """Route for updating API keys"""
    api_key_repo = APIKeyRepository(db=db)

    if not api_key_repo:
        raise HTTPError(details="API key repository is not available.")

    if input_data.id is None:
        raise HTTPError(
            status_code=status.HTTP_400_BAD_REQUEST, details="API key ID is required."
        )

    if client.id is None:
        raise HTTPError(
            status_code=status.HTTP_400_BAD_REQUEST, details="Client ID is required."
        )

    updated_api_key = await api_key_repo.aupdate_api_key(
        key_id=input_data.id,
        client_id=client.id,
        update_data=input_data.model_dump(exclude={"id"}),
    )

    if not updated_api_key:
        raise HTTPError(
            status_code=status.HTTP_404_NOT_FOUND, details="API key not found."
        )

    return APIResponseSchema(
        id=updated_api_key.id,
        name=updated_api_key.name,
        prefix=updated_api_key.key_prefix,
        full_key=f"{updated_api_key.key_prefix}...",  # Don't return full key!
        owner=client.external_id,
        created_at=updated_api_key.created_at,
        updated_at=datetime.now(),
        expires_at=updated_api_key.expires_at,
        scopes=updated_api_key.scopes,
    )


@router.delete("/apikeys/{api_key_id}", status_code=status.HTTP_200_OK)
async def deregister_apikey(
    api_key_id: int = Path(..., description="ID of the API key to de-register."),
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
    client: ClientSchema = Depends(get_current_active_user),
) -> dict[str, str]:
    """Route for de-registering API keys by the api key id. it ensures that only the
    owner can deregister their API keys."""
    api_key_repo = APIKeyRepository(db=db)

    if not api_key_repo:
        raise HTTPError(details="API key repository is not available.")

    deleted = await api_key_repo.adelete_owned_key(
        key_id=api_key_id, owner_id=int(client.id) if client.id is not None else 0
    )

    if not deleted:
        raise HTTPError(
            status_code=status.HTTP_404_NOT_FOUND, details="API key not found."
        )

    return {"message": "API key deregistered successfully."}
