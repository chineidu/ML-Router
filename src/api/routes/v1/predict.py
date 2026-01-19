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

    backend_url = await backend_registry.aget_endpoint(model_type)
    if not backend_url:
        raise HTTPError(
            details=f"No healthy backend available for model type '{model_type}'.",
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
    if response.status_code != 200:
        raise HTTPError(
            details=f"Backend error: {response.text}",
        )
    backend_data = response.json()

    return InferenceResponseSchema(
        request_id=request_id,
        model_type=model_type,
        model_version=backend_data.get("modelVersion", ""),
        prediction=backend_data.get("prediction", {}),
        processing_time_ms=(time.perf_counter() - start_time) * 1000,
        backend_endpoint=backend_url,
    )
