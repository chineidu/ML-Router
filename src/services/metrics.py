import asyncio
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from src import create_logger
from src.utilities.utils import calculate_latency_ewma

if TYPE_CHECKING:
    from src.schemas.backend_registry import ServiceInstance
    from src.services.service_discovery import BackendRegistry


logger = create_logger(name=__name__)
tracer = trace.get_tracer(__name__)


async def update_metrics_background(
    backend_registry: "BackendRegistry",
    instance: "ServiceInstance",
    service_id: str,
    latency_ms: float,
) -> None:
    """Background task to update backend instance metrics."""
    with tracer.start_as_current_span("update_metrics_background") as span:
        span.set_attribute("service_id", service_id)
        span.set_attribute("backend.url", instance.endpoint_url)

        try:
            # Update latency using Exponential Weighted Moving Average (EWMA)
            old_latency: float = float(instance.runtime_metrics.latency_ms or 120)
            new_latency: float = calculate_latency_ewma(
                old_latency, current_latency=latency_ms
            )
            span.set_attribute("old_latency_ms", old_latency)
            span.set_attribute("new_latency_ms", new_latency)
            instance.runtime_metrics.latency_ms = new_latency

            # Dynamic weight calculation
            instance.runtime_metrics.weight = (
                backend_registry.service_registry.compute_dynamic_weight(instance)
            )

            # Debounced save to registry
            asyncio.create_task(
                backend_registry.service_registry.asave_registry_debounced(delay=5)
            )
            span.add_event("metrics_updated")
            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            logger.error(
                f"Error updating service '{service_id}' metrics in background: {e}"
            )
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
