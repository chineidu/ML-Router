from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src import create_logger
from src.api.core.auth import (
    get_current_admin_user,
)
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import get_rate_limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.config import app_settings
from src.db.models import DBClient, aget_db
from src.db.repositories.client_repository import ClientRepository
from src.schemas.db.models import ClientSchema
from src.schemas.routes.admin import (
    ClientListResponseSchema,
    ClientResponseSchema,
    UpdateClientSchema,
)

if TYPE_CHECKING:
    pass

logger = create_logger(name=__name__)
ACCESS_TOKEN_EXPIRE_MINUTES: int = app_settings.ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(tags=["admin"], default_response_class=MsgSpecJSONResponse)


@router.get("/admin/users", status_code=status.HTTP_200_OK)
async def list_users(
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of users to return"
    ),
    cursor: int | None = Query(
        default=None, description="Last seen user ID for pagination"
    ),
    admin: ClientSchema = Depends(get_current_admin_user),  # noqa: ARG001
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
) -> ClientListResponseSchema:
    """List all users with cursor-based pagination."""
    client_repo = ClientRepository(db=db)

    if not client_repo:
        raise HTTPError(details="Client repository is not available.")

    # Fetch clients using cursor pagination
    clients, next_cursor = await client_repo.aget_clients_cursor(
        limit=limit, last_seen_id=cursor
    )

    # Convert to response schemas
    client_responses = [
        ClientResponseSchema.model_validate(client) for client in clients
    ]

    return ClientListResponseSchema(
        clients=client_responses,
        next_cursor=next_cursor,
        count=len(client_responses),
    )


@router.post("/admin/users", status_code=status.HTTP_200_OK)
async def update_client_data(
    input_data: UpdateClientSchema,
    admin: ClientSchema = Depends(get_current_admin_user),  # noqa: ARG001
    db: AsyncSession = Depends(aget_db),
    rate_limiter=Depends(get_rate_limiter),  # noqa: ANN001, ARG001
) -> ClientResponseSchema:
    """Update client data."""
    # Check if name exists
    client_repo = ClientRepository(db=db)

    if not client_repo:
        raise HTTPError(details="Client repository is not available.")

    db_client: DBClient | None = await client_repo.aget_client_by_id(id=input_data.id)
    if not db_client:
        raise HTTPError(
            status_code=status.HTTP_400_BAD_REQUEST,
            details="Client not found.",
        )
    await client_repo.aupdate_client(
        client_id=input_data.id, update_data=input_data.model_dump(exclude={"id"})
    )

    db_client = await client_repo.aget_client_by_id(id=input_data.id)
    if not db_client:
        raise HTTPError(
            status_code=status.HTTP_400_BAD_REQUEST,
            details="Client not found after update.",
        )

    return ClientResponseSchema.model_validate(db_client)
