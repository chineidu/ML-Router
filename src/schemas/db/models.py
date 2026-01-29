from datetime import datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import ConfigDict, EmailStr, Field, SecretStr

from src.schemas.base import BaseSchema
from src.schemas.types import ClientStatusEnum, TierEnum


class BaseClientSchema(BaseSchema):
    """Schema representing a client."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int | None = Field(default=None)
    external_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    email: EmailStr
    tier: TierEnum = Field(default=TierEnum.FREE)
    credits: float = Field(default=0.0, le=1_000_000.0, ge=0.0)
    status: ClientStatusEnum = Field(default=ClientStatusEnum.ACTIVE)
    is_active: bool = Field(default=True)
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class GuestClientSchema(BaseSchema):
    """Schema representing a guest/anonymous user with limited access."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int | None = None
    external_id: str = "guest"
    name: str = "guest"
    email: EmailStr = Field(default="guest@anonymous.local")
    tier: TierEnum = Field(default=TierEnum.GUEST)
    credits: float = Field(default=0.0)
    status: ClientStatusEnum = Field(default=ClientStatusEnum.ACTIVE)
    is_active: bool = Field(default=True)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ClientCreateSchema(BaseClientSchema):
    """Schema representing a database client with password."""

    password: SecretStr

    # Fetching and updating model config to add example
    _custom_model_config: ClassVar[ConfigDict] = BaseSchema.model_config.copy()
    _json_schema_extra: ClassVar[dict[str, Any]] = {
        "example": {
            "name": "example_user",
            "email": "user@example.com",
            "password": "securepassword123",
        }
    }
    _custom_model_config.update({"json_schema_extra": _json_schema_extra})
    model_config = _custom_model_config


class ClientSchema(ClientCreateSchema):
    """Schema representing a database client."""

    password_hash: str


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
    requests_per_minute: int = Field(default=60)
    is_active: bool = Field(default=True)
    created_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
