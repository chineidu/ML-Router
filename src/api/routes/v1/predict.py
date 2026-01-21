import time
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from src import create_logger
from src.api.core.dependencies import get_backend_registry, get_client, get_request_id
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.config import app_config
from src.schemas.input_schema import InferenceRequest
from src.schemas.response import InferenceResponseSchema
from src.schemas.types import ModelTypeEnum
from src.utilities.utils import calculate_latency

if TYPE_CHECKING:
    import httpx

    from src.services.service_discovery import BackendRegistry

logger = create_logger(name=__name__)
LIMIT_VALUE: int = app_config.api_config.ratelimit.default_rate
router = APIRouter(tags=["predict"], default_response_class=MsgSpecJSONResponse)


@router.post("/predict/{model_type}", status_code=status.HTTP_200_OK)
@limiter.limit(f"{LIMIT_VALUE}/minute")
async def make_prediction(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    model_type: Annotated[
        ModelTypeEnum, Path(description="Type of model to use for prediction.")
    ],
    input_data: InferenceRequest,  # noqa: ARG001
    aclient: "httpx.AsyncClient" = Depends(get_client),
    backend_registry: "BackendRegistry" = Depends(get_backend_registry),
    request_id: str = Depends(get_request_id),
) -> InferenceResponseSchema:
    """Route for making predictions"""

    start_time: float = time.perf_counter()
    strategy = app_config.load_balancer_config.strategy
    logger.debug(
        f"Received prediction request | model_type='{model_type}' | strategy={strategy}"
    )

    backend_url, instance = await backend_registry.aselect_backend_endpoint(
        model_type, strategy=strategy
    )
    if not backend_url or not instance:
        raise HTTPError(
            details=f"No healthy backend available for model type '{model_type}'.",
        )

    try:
        # Increment counter
        await backend_registry.aupdate_active_connection(
            service_id=instance.service_id, delta=1, persist=False
        )

        # Prepare payload for backend
        payload = {
            "input_data": input_data.input_data,
            "model_version": input_data.model_version,
        }
        # Forward request to backend
        response = await aclient.post(
            url=backend_url,
            json=payload,
        )
        if response.status_code != status.HTTP_200_OK:
            raise HTTPError(
                details=f"Backend error: {response.text}",
            )
        backend_data = response.json()
    finally:
        # Decrement counter (even if error occurs)
        await backend_registry.aupdate_active_connection(
            service_id=instance.service_id, delta=-1, persist=False
        )
        latency_ms: float = (time.perf_counter() - start_time) * 1000
        # update latency using EWMA
        old_latency: float = float(instance.runtime_metrics.latency_ms or 120)
        new_latency: float = calculate_latency(old_latency, current_latency=latency_ms)
        instance.runtime_metrics.latency_ms = new_latency

        # Compute dynamic weight based on current state
        instance.runtime_metrics.weight = (
            backend_registry.service_registry.compute_dynamic_weight(instance)
        )
        # Persist updated instance info
        await backend_registry.service_registry.asave_registry()

    return InferenceResponseSchema(
        request_id=request_id,
        model_type=model_type,
        model_version=backend_data.get("modelVersion", ""),
        prediction=backend_data.get("prediction", {}),
        processing_time_ms=latency_ms,
        backend_endpoint=backend_url,
    )
