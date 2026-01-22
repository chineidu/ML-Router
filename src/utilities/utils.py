import asyncio
import hashlib
import time
from typing import TYPE_CHECKING, Any

import httpx
import msgspec
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src import create_logger
from src.schemas.types import CircuitBreakerStateEnum

if TYPE_CHECKING:
    from src.schemas.backend_registry import ServiceInstance
    from src.services.service_discovery import BackendRegistry

logger = create_logger(name=__name__)
# JSON encoder
msgspec_encoder = msgspec.json.Encoder()

# JSON decoder
msgspec_decoder = msgspec.json.Decoder()


def sort_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sort a dictionary by its keys.

    Parameters
    ----------
    data : dict[str, Any]
        The dictionary to sort.

    Returns
    -------
    dict[str, Any]
        A new dictionary with keys sorted recursively.
    """
    # Base case: if the data is not a dictionary, return it as is
    if not isinstance(data, dict):
        return data
    # Recursive case: sort the dictionary
    return {key: sort_dict(data[key]) for key in sorted(data)}


def generate_idempotency_key(
    payload: dict[str, Any], user_id: str | None = None
) -> str:
    """Generate an idempotency key based on the payload and optional user ID."""
    hasher = hashlib.sha256()
    if user_id:
        data: dict[str, Any] = {"payload": payload, "user_id": user_id}
    else:
        data = {"payload": payload}

    # Serialize the payload using msgspec for consistent hashing
    serialized_payload = msgspec_encoder.encode(sort_dict(data))
    hasher.update(serialized_payload)

    return hasher.hexdigest()


def calculate_latency_ewma(
    old_latency: float | None, current_latency: float, alpha: float = 0.2
) -> float:
    """
    Calculates the exponentially weighted moving average latency (EWMA).
    Using EWMA helps to smooth out short-term fluctuations and highlight
    longer-term trends in latency.
    """
    if not old_latency:
        return round(current_latency, 2)

    new_latency = (alpha * current_latency) + ((1 - alpha) * old_latency)
    return round(new_latency, 2)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state: CircuitBreakerStateEnum = CircuitBreakerStateEnum.CLOSED
        self.last_failure_time: float | None = None
        logger.info(
            f"Circuit Breaker initialized with failure_threshold={self.failure_threshold}, "
            f"recovery_timeout={self.recovery_timeout} seconds."
        )

    def record_failure(self) -> None:
        """Record a failure, update the circuit breaker state and last failure time"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerStateEnum.OPEN
            logger.error(
                f"🔴 Circuit Breaker tripped ({CircuitBreakerStateEnum.OPEN.name}). Not accepting requests."
            )

    def record_success(self) -> None:
        """Record a success and reset the circuit breaker if in HALF_OPEN state"""
        if self.state == CircuitBreakerStateEnum.HALF_OPEN:
            logger.info(
                f"🟢 Circuit Breaker reset ({CircuitBreakerStateEnum.CLOSED.name}). Accepting requests."
            )

        # Clear count
        self.failure_count = 0
        self.state = CircuitBreakerStateEnum.CLOSED
        logger.info(
            f"🟢 Circuit Breaker reset ({CircuitBreakerStateEnum.CLOSED.name}). Accepting requests."
        )

    def can_execute(self) -> bool:
        """Check if requests can be executed based on the circuit breaker state"""
        if self.state == CircuitBreakerStateEnum.CLOSED:
            return True

        if (
            self.state == CircuitBreakerStateEnum.OPEN
            and self.last_failure_time is not None
            and (time.time() - self.last_failure_time > self.recovery_timeout)
        ):
            self.state = CircuitBreakerStateEnum.HALF_OPEN
            logger.warning(
                f"🟠 Circuit Breaker is {CircuitBreakerStateEnum.HALF_OPEN.name}. Testing recovery..."
            )
            return True

        return self.state == CircuitBreakerStateEnum.CLOSED


async def aretriable_request(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    max_attempts: int = 3,
    multiplier: float = 0.5,
    min_wait: float = 1,
    max_wait: float = 5,
) -> httpx.Response | None:
    """Make an HTTP POST request with retries on connection-related errors.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    url : str
        The URL to send the request to.
    payload : dict[str, Any]
        The JSON payload to include in the request body.
    max_attempts : int, optional
        Maximum number of retry attempts (default is 3).
    multiplier : float, optional
        Multiplier for exponential backoff (default is 0.5).
    min_wait : float, optional
        Minimum wait time between retries in seconds (default is 1).
    max_wait : float, optional
        Maximum wait time between retries in seconds (default is 5).

    Returns
    -------
    httpx.Response | None
        The HTTP response if the request was successful, otherwise None.
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)
        ),
        reraise=True,
    ):
        with attempt:
            return await client.post(url, json=payload)
    return None


async def update_metrics_background(
    backend_registry: "BackendRegistry",
    instance: "ServiceInstance",
    service_id: str,
    latency_ms: float,
) -> None:
    """Background task to update backend instance metrics."""
    try:
        # Update latency using Exponential Weighted Moving Average (EWMA)
        old_latency: float = float(instance.runtime_metrics.latency_ms or 120)
        new_latency: float = calculate_latency_ewma(
            old_latency, current_latency=latency_ms
        )
        instance.runtime_metrics.latency_ms = new_latency

        # Dynamic weight calculation
        instance.runtime_metrics.weight = (
            backend_registry.service_registry.compute_dynamic_weight(instance)
        )

        # Debounced save to registry
        asyncio.create_task(
            backend_registry.service_registry.asave_registry_debounced(delay=5)
        )

    except Exception as e:
        logger.error(
            f"Error updating service '{service_id}' metrics in background: {e}"
        )
