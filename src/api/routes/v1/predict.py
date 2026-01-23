import asyncio
import time
from typing import TYPE_CHECKING, Annotated

from aiocache import Cache
from fastapi import APIRouter, Depends, Path, Request, status

from src import create_logger
from src.api.core.cache import cached
from src.api.core.dependencies import (
    get_backend_registry,
    get_cache,
    get_client,
    get_request_id,
)
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.config import app_config
from src.schemas.input_schema import InferenceRequest
from src.schemas.response import InferenceResponseSchema
from src.schemas.types import ModelTypeEnum
from src.utilities.utils import aretriable_request, update_metrics_background

if TYPE_CHECKING:
    import httpx

    from src.services.service_discovery import BackendRegistry
    from src.utilities.circuit_breaker import CircuitBreaker

logger = create_logger(name=__name__)
LIMIT_VALUE: int = app_config.api_config.ratelimit.burst_rate
router = APIRouter(tags=["predict"], default_response_class=MsgSpecJSONResponse)


@router.post("/predict/{model_type}", status_code=status.HTTP_200_OK)
@cached(ttl=600, key_prefix="predict", payload_key="input_data")
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
    cache: Cache = Depends(get_cache),  # Required by caching decorator  # noqa: ARG001
) -> InferenceResponseSchema:
    """
    Perform model inference and return a prediction with idempotency and caching.

    This endpoint forwards the inference request to the appropriate backend service
    based on the `model_type`.

    Caching & Idempotency:
    ----------------------
    Although `POST` requests are typically non-idempotent, this endpoint is idempotent
    because the same input data always yields the same prediction.
    - **Mechanism:** Uses a Redis-backed cache to store results.
    - **Key Generation:** An idempotency key is generated from the `input_data` payload.
    - **TTL:** Cached results expire after 600 seconds (10 minutes) to ensure freshness.

    Parameters:
    -----------
    - **model_type**: The specific machine learning model to target (e.g., sentiment, classification).
    - **input_data**: The JSON payload containing the data to be processed.

    Returns:
    --------
    - **InferenceResponseSchema**: The prediction result, metadata, and execution latency.
    """

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

    circuit_breaker: "CircuitBreaker" = instance.circuit_breaker

    try:
        if not circuit_breaker.can_execute:
            raise HTTPError(details="Uxexpected error")

        # ---------- Continue if circuit is CLOSED/HALF_OPEN
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
        response = await aretriable_request(
            client=aclient,
            url=backend_url,
            payload=payload,
            # Retry parameters
            circuit_breaker=circuit_breaker,
            max_attempts=3,
            multiplier=0.5,
            min_wait=1,
            max_wait=5,
        )
        if response is None or response.status_code != status.HTTP_200_OK:
            raise HTTPError(
                details=f"Backend error: {response.text if response else 'No response received'}",
            )
        backend_data = response.json()
    finally:
        # Decrement counter (even if error occurs)
        await backend_registry.aupdate_active_connection(
            service_id=instance.service_id, delta=-1, persist=False
        )
        latency_ms: float = (time.perf_counter() - start_time) * 1000

        # Run updates in background
        asyncio.create_task(
            update_metrics_background(
                backend_registry=backend_registry,
                instance=instance,
                service_id=instance.service_id,
                latency_ms=latency_ms,
            )
        )

    return InferenceResponseSchema(
        request_id=request_id,
        model_type=model_type,
        model_version=backend_data.get("modelVersion", ""),
        prediction=backend_data.get("prediction", {}),
        processing_time_ms=latency_ms,
        backend_endpoint=backend_url,
    )
