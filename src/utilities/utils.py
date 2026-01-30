import asyncio
import hashlib
import re
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
from src.api.core.exceptions import CircuitOpenError
from src.schemas.types import CircuitBreakerStateEnum, TierEnum
from src.utilities.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from src.schemas.backend_registry import ServiceInstance
    from src.services.service_discovery import BackendRegistry

logger = create_logger(name=__name__)
# JSON encoder
MSGSPEC_ENCODER = msgspec.json.Encoder()

# JSON decoder
MSGSPEC_DECODER = msgspec.json.Decoder()


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
    serialized_payload = MSGSPEC_ENCODER.encode(sort_dict(data))
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


async def aretriable_request(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    circuit_breaker: CircuitBreaker | None = None,
    max_attempts: int = 3,
    multiplier: float = 0.5,
    min_wait: float = 1,
    max_wait: float = 5,
) -> httpx.Response | None:
    """Make an HTTP POST request with retries and optional circuit breaker.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    url : str
        The URL to send the request to.
    payload : dict[str, Any]
        The JSON payload to include in the request body.
    circuit_breaker : CircuitBreaker | None, optional
        An optional CircuitBreaker instance to manage request flow.
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
            if circuit_breaker and not circuit_breaker.can_execute():
                raise CircuitOpenError(
                    details=f"Circuit breaker is {CircuitBreakerStateEnum.OPEN.name}. Request blocked."
                )
            response = await client.post(url, json=payload)

            # 5xx errors are retriable while 4xx are not
            if circuit_breaker:
                # Successful response
                if 200 <= response.status_code < 300:
                    circuit_breaker.record_success()
                # Server error
                elif 500 <= response.status_code < 600:
                    circuit_breaker.record_failure()
                    # Raise for retry
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                else:  # Client error (4xx)
                    circuit_breaker.record_failure()
            return response
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


def get_ratelimit_value(tier: TierEnum) -> str:
    """Get the rate limit value based on the client tier.

    Parameters
    ----------
    tier : TierEnum
        The tier of the client.

    Returns
    -------
    str
        The rate limit string (e.g., "10/minute").
    """

    if tier == TierEnum.GUEST:
        return "10/minute"
    if tier == TierEnum.FREE:
        return "20/minute"
    if tier == TierEnum.PLUS:
        return "60/minute"
    if tier == TierEnum.PRO:
        return "120/minute"

    # Default to FREE tier limits
    return "10/minute"


def extract_rate_limit_number(tier: TierEnum, default: int = 5) -> int:
    """Extract the numerical rate limit from the rate limit string for a given tier.

    Parameters
    ----------
    tier : TierEnum
        The tier of the client.
    default : int, optional
        The default rate limit number to return if extraction fails, by default 5

    Returns
    -------
    int
        The numerical rate limit extracted from the rate limit string.
    """
    pattern = r"\d{1,3}"
    limit_rate = get_ratelimit_value(tier)

    # Extract number from rate limit string
    match = re.search(pattern, string=limit_rate)
    if match:
        result = match.group()
    else:
        # Handle the case where no match is found
        result = default

    return int(result)
