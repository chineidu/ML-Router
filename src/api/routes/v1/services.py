from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from src import create_logger
from src.api.core.dependencies import get_backend_registry, get_service_registry
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.config import app_config
from src.schemas.routes.services import (
    ServiceDeregistrationResponseSchema,
    ServiceRemovalSchema,
    ServiceRequestSchema,
    ServiceResponseSchema,
)

if TYPE_CHECKING:
    from src.services.service_discovery import BackendRegistry, ServiceRegistry

router = APIRouter(tags=["services"], default_response_class=MsgSpecJSONResponse)
logger = create_logger(name=__name__)
LIMIT_VALUE: int = app_config.api_config.ratelimit.default_rate


@limiter.limit(f"{LIMIT_VALUE}/minute")
@router.post("/services", status_code=status.HTTP_200_OK)
async def register_service(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    input_data: ServiceRequestSchema,
    backend_registry: "BackendRegistry" = Depends(get_backend_registry),
    service_registry: "ServiceRegistry" = Depends(get_service_registry),
) -> ServiceResponseSchema:
    """Route for registering service instances"""
    if not backend_registry:
        raise HTTPError(details="Backend registry is not available.")
    success = await service_registry.abatch_register(input_data.services)
    if not success:
        raise HTTPError(details="Failed to register services.")

    return ServiceResponseSchema(
        message="Services registered successfully.",
        num_registered_services=len(input_data.services),
    )


@router.get("/services/list", status_code=status.HTTP_200_OK)
@limiter.limit(f"{LIMIT_VALUE}/minute")
async def list_services(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    backend_registry: "BackendRegistry" = Depends(get_backend_registry),
    service_registry: "ServiceRegistry" = Depends(get_service_registry),
) -> ServiceResponseSchema:
    """Route for listing registered service instances"""
    if not backend_registry:
        raise HTTPError(details="Backend registry is not available.")
    if not service_registry:
        raise HTTPError(details="Service registry is not available.")
    services = service_registry.list_all_services()
    num_services = sum(len(instances) for instances in services.values())
    if not services:
        raise HTTPError(details="No services found in the registry.")
    return ServiceResponseSchema(
        message="Services retrieved successfully.",
        num_registered_services=num_services,
        registered_services=services,
    )


@limiter.limit(f"{LIMIT_VALUE}/minute")
@router.delete("/services", status_code=status.HTTP_200_OK)
async def deregister_service(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    input_data: ServiceRemovalSchema,
    backend_registry: "BackendRegistry" = Depends(get_backend_registry),
    service_registry: "ServiceRegistry" = Depends(get_service_registry),
) -> ServiceDeregistrationResponseSchema:
    """Route for deregistering service instances"""
    if not backend_registry:
        raise HTTPError(details="Backend registry is not available.")
    success = await service_registry.abatch_deregister(input_data.services)
    if not success:
        raise HTTPError(details="Failed to deregister services.")

    return ServiceDeregistrationResponseSchema(
        message="Services deregistered successfully.",
        deregistered_services=len(input_data.services),
    )


@limiter.limit(f"{LIMIT_VALUE}/minute")
@router.get("/services/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    service_id: Annotated[
        str,
        Query(
            description="Unique identifier for the service instance to check heartbeat."
        ),
    ],
    backend_registry: "BackendRegistry" = Depends(get_backend_registry),
    service_registry: "ServiceRegistry" = Depends(get_service_registry),
) -> dict[str, Any]:
    """Route for checking heartbeat of service instances."""
    if not backend_registry:
        raise HTTPError(details="Backend registry is not available.")
    success = await service_registry.aheartbeat(service_id)
    if not success:
        raise HTTPError(
            details=f"Failed to process heartbeat for service ID '{service_id}'."
        )

    return {"message": f"Heartbeat received for service ID {service_id}."}
