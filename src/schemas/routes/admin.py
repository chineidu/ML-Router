from datetime import datetime
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from src.schemas.base import BaseSchema
from src.schemas.types import ClientStatusEnum, RoleTypeEnum, TierEnum


class UpdateClientSchema(BaseSchema):
    """Schema for updating client information."""

    id: int
    tier: TierEnum | None = Field(default=None)
    roles: list[RoleTypeEnum] | None = Field(default=None)
    status: ClientStatusEnum | None = Field(default=None)
    credits: float | None = Field(default=None, le=1_000_000.0, ge=0.0)
    is_active: bool

    # Fetching and updating model config to add example
    _custom_model_config: ClassVar[ConfigDict] = BaseSchema.model_config.copy()
    _json_schema_extra: ClassVar[dict[str, Any]] = {
        "example": {
            "id": 1,
            "tier": "free",
            "roles": ["user"],
            "status": "active",
            "credits": 1.0,
            "is_active": True,
        }
    }
    _custom_model_config.update({"json_schema_extra": _json_schema_extra})
    model_config = _custom_model_config


class ClientResponseSchema(BaseSchema):
    """Schema for client response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int
    external_id: str
    name: str
    email: str
    tier: TierEnum
    roles: list[RoleTypeEnum]
    credits: float
    status: ClientStatusEnum
    is_active: bool
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

    @field_validator("roles", mode="before")
    @classmethod
    def convert_roles(cls, v: Any) -> list[RoleTypeEnum]:
        """Convert DBRole objects or strings to RoleTypeEnum."""
        if not v:
            return []

        result = []
        for role in v:
            if isinstance(role, str):
                result.append(RoleTypeEnum(role))
            elif hasattr(role, "name"):  # DBRole object
                result.append(RoleTypeEnum(role.name))
            else:
                result.append(role)
        return result


class ClientListResponseSchema(BaseSchema):
    """Schema for paginated client list response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    clients: list[ClientResponseSchema]
    next_cursor: int | None = Field(
        default=None, description="ID of last client for pagination"
    )
    count: int = Field(description="Number of clients in this response")
