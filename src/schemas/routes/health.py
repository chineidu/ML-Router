import pendulum
from pydantic import Field

from src.schemas.base import BaseSchema


class HealthCheckSchema(BaseSchema):
    """Schema for health check response."""

    status: str = Field(description="Health status of the service.")
    timestamp: str = Field(
        default_factory=lambda: pendulum.now().to_iso8601_string(),
        description="Timestamp of the health check in ISO 8601 format.",
    )
    backends: dict[str, str] = Field(description="Status of backend services.")
