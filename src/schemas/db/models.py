from datetime import datetime
from uuid import uuid4

from pydantic import ConfigDict, Field

from src.schemas.base import BaseSchema
from src.schemas.types import ClientStatusEnum, TierEnum


class ClientSchema(BaseSchema):
    """Schema representing a database client."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int | None = None
    external_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    tier: TierEnum
    credits: float = 0.0
    status: ClientStatusEnum
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiKeySchema(BaseSchema):
    """Schema representing a database API key."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int | None = None
    client_id: int
    key_prefix: str
    key_hash: str
    name: str
    scopes: list[str] = Field(default_factory=list)
    requests_per_minute: int = 60
    active: bool = True
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
