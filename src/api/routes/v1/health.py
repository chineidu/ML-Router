from aiocache import Cache
from fastapi import APIRouter, Depends, Request, status

from src import create_logger
from src.api.core.cache import cached
from src.api.core.dependencies import get_backend_registry, get_cache
from src.api.core.exceptions import HTTPError
from src.api.core.ratelimit import limiter
from src.api.core.responses import MsgSpecJSONResponse
from src.config import app_config
from src.schemas.routes.health import HealthStatusSchema
from src.services.service_discovery import BackendRegistry

logger = create_logger(name=__name__)
LIMIT_VALUE: int = app_config.api_config.ratelimit.default_rate
router = APIRouter(tags=["health"], default_response_class=MsgSpecJSONResponse)
TTL: int = 30  # seconds


@router.get("/health", status_code=status.HTTP_200_OK)
@cached(ttl=TTL, key_prefix="health")
@limiter.limit(f"{LIMIT_VALUE}/minute")
async def health_check(
    request: Request,  # Required by SlowAPI  # noqa: ARG001
    cache: Cache = Depends(get_cache),  # Required by caching decorator  # noqa: ARG001
    backend_registry: BackendRegistry = Depends(get_backend_registry),
) -> HealthStatusSchema:
    """Route for health checks"""

    # Collect backend status
    backends: dict[str, str] = {}
    services = backend_registry.service_registry.list_all_services()
    for service_name, instances in services.items():
        healthy_count = sum(1 for inst in instances if inst.status.value == "healthy")
        total_count = len(instances)
        backends[service_name] = f"{healthy_count}/{total_count} healthy"

    response = HealthStatusSchema(
        name=app_config.api_config.title,
        status=app_config.api_config.status,
        version=app_config.api_config.version,
        backends=backends,
    )

    if not response:
        raise HTTPError(
            details="Health check failed",
        )

    return response
