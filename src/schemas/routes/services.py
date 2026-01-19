from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from src.schemas.backend_registry import ServiceInstance
from src.schemas.base import BaseSchema


class ServiceRequestSchema(BaseSchema):
    services: list[ServiceInstance] = Field(
        description="List of service instances to be registered."
    )

    # Fetching and updating model config to add example
    _custom_model_config: ClassVar[ConfigDict] = BaseSchema.model_config.copy()
    _json_schema_extra: ClassVar[dict[str, Any]] = {
        "example": {
            "services": [
                {
                    "service_id": "model_service_1",
                    "service_name": "classification",
                    "host": "v1.0.0",
                    "port": 6500,
                    "protocol": "http",
                    "health_check_url": "http://localhost:6500/health",
                    "metadata": {
                        "container_id": "abc123def456",
                        "container_name": "model_service_container",
                        "compose_service": "model_service",
                        "image": "model_service_image:latest",
                        "model_version": "v1.0.0",
                    },
                },
                {
                    "service_id": "model_service_2",
                    "service_name": "sentiment",
                    "host": "v2.1.0",
                    "port": 6600,
                    "protocol": "http",
                    "health_check_url": "http://localhost:6600/health",
                    "metadata": {
                        "container_id": "def456ghi789",
                        "container_name": "sentiment_service_container",
                        "compose_service": "sentiment_service",
                        "image": "sentiment_service_image:latest",
                        "model_version": "v2.1.0",
                    },
                },
            ]
        }
    }
    _custom_model_config.update({"json_schema_extra": _json_schema_extra})
    model_config = _custom_model_config


class ServiceRemovalSchema(BaseSchema):
    services: list[str] = Field(
        description="List of service instances to be deregistered."
    )

    # Fetching and updating model config to add example
    _custom_model_config: ClassVar[ConfigDict] = BaseSchema.model_config.copy()
    _json_schema_extra: ClassVar[dict[str, Any]] = {
        "example": {"services": ["model_service_1", "model_service_2"]}
    }
    _custom_model_config.update({"json_schema_extra": _json_schema_extra})
    model_config = _custom_model_config


class ServiceResponseSchema(BaseSchema):
    message: str = Field(
        description="Response message indicating the result of the service registration."
    )
    num_registered_services: int = Field(
        description="Number of services that were successfully registered."
    )
    registered_services: dict[str, list[ServiceInstance]] | None = Field(
        default=None,
        description="Dictionary categorizing registered services by their service names.",
    )


class ServiceDeregistrationResponseSchema(BaseSchema):
    message: str = Field(
        description="Response message indicating the result of the service deregistration."
    )
    deregistered_services: int = Field(
        description="Number of services that were successfully deregistered."
    )
