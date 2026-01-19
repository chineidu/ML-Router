from typing import Any

import pendulum
from pydantic import Field

from src.schemas.base import BaseSchema, Float
from src.schemas.types import ModelTypeEnum


class InferenceResponseSchema(BaseSchema):
    """Schema for an inference response."""

    request_id: str = Field(description="Unique identifier for the inference request.")
    model_type: ModelTypeEnum = Field(
        description="The type of model used for inference.", validate_default=True
    )
    model_version: str = Field(description="Version of the model used for inference.")
    prediction: dict[str, Any] = Field(
        description="The prediction result from the model inference."
    )
    processing_time_ms: Float = Field(
        description="Time taken to process the inference request in milliseconds."
    )
    timestamp: str = Field(
        default_factory=lambda: pendulum.now().to_iso8601_string(),
        description="Timestamp of the response in ISO 8601 format.",
    )
    backend_endpoint: str = Field(
        description="The backend endpoint that processed the inference request."
    )
