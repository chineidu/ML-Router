from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from src.schemas.base import BaseSchema
from src.schemas.types import ModelTypeEnum


class InferenceRequest(BaseSchema):
    """Schema for an inference request."""

    model_type: ModelTypeEnum = Field(
        description="The type of model to use for inference.", validate_default=True
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

    # Fetching and updating model config to add example
    _custom_model_config: ClassVar[ConfigDict] = BaseSchema.model_config.copy()
    _json_schema_extra: ClassVar[dict[str, Any]] = {
        "example": {
            "model_type": "sentiment",
            "input_data": {"text": "I love using this ML model router!"},
            "model_version": "v1.0.0",
            "timeout": 10,
        }
    }
    _custom_model_config.update({"json_schema_extra": _json_schema_extra})
    model_config = _custom_model_config
