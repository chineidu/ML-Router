from typing import Any

from pydantic import Field, field_validator

from src.schemas.base import BaseSchema
from src.schemas.types import ModelTypeEnum


class InferenceRequest(BaseSchema):
    """Schema for an inference request."""

    model_type: ModelTypeEnum = Field(
        description="The type of model to use for inference."
    )
    input_data: dict[str, Any] = Field(
        description="The input data for the model inference."
    )
    model_version: str | None = Field(
        None, description="Optional version of the model to use for inference."
    )
    timeout: int | None = Field(
        None,
        description="Optional timeout in seconds for the inference request.",
        ge=1,
        le=120,
    )

    @field_validator("input_data", mode="before")
    @classmethod
    def validate_input_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validates that input_data is not empty."""
        if not v:
            raise ValueError("input_data must not be empty.")
        return v
