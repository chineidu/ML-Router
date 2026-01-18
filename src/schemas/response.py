from typing import Any

import pendulum
from pydantic import Field, field_validator

from src.schemas.base import BaseSchema
from src.schemas.types import ModelTypeEnum


class InferenceResponse(BaseSchema):
    """Schema for an inference response."""

    request_id: str = Field(description="Unique identifier for the inference request.")
    model_type: ModelTypeEnum = Field(
        description="The type of model used for inference."
    )
    model_version: str = Field(description="Version of the model used for inference.")
    prediction: dict[str, Any] = Field(
        description="The prediction result from the model inference."
    )
    processing_time_ms: float = Field(
        description="Time taken to process the inference request in milliseconds."
    )
    timestamp: str = Field(
        default_factory=lambda: pendulum.now().to_iso8601_string(),
        description="Timestamp of the response in ISO 8601 format.",
    )
    backend_endpoint: str = Field(
        description="The backend endpoint that processed the inference request."
    )

    @field_validator("model_type", mode="after")
    @classmethod
    def validate_model_type(cls, v: ModelTypeEnum) -> str:
        """Ensures model_type is a valid ModelTypeEnum value."""
        if v not in ModelTypeEnum:
            raise ValueError(
                f"Invalid model_type: {v}. Must be one of {list(ModelTypeEnum)}."
            )
        return v
