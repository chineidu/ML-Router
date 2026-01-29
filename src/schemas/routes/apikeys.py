from datetime import datetime

from pydantic import ConfigDict, Field

from src.schemas.base import BaseSchema
from src.schemas.types import APIKeyScopeEnum


class APICreationSchema(BaseSchema):
    """Schema representing the creation of an API key."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )
    name: str = Field(description="Name of the API key to be created.")
    expires_at: datetime | None = Field(
        default=None, description="Expiration date and time of the API key."
    )
    scopes: list[APIKeyScopeEnum] = Field(
        description="List of scopes/permissions assigned to the API key."
    )


class APIResponseSchema(BaseSchema):
    """Schema representing an API key."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat() if v else None},
    )

    id: int = Field(description="Unique identifier of the API key.")
    name: str = Field(description="Name of the API key.")
    prefix: str = Field(description="Prefix of the API key.")
    full_key: str = Field(description="Full API key value.")
    owner: str = Field(description="External ID of the API key owner.")
    created_at: datetime | None = Field(
        description="Creation date and time of the API key."
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Last update date and time of the API key.",
    )
    expires_at: datetime | None = Field(
        default=None, description="Expiration date and time of the API key."
    )
    scopes: list[APIKeyScopeEnum] = Field(
        description="List of scopes/permissions assigned to the API key."
    )
