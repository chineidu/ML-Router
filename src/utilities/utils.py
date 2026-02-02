import hashlib
import re
from typing import TYPE_CHECKING, Any

import httpx
import msgspec
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
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
    pass

logger = create_logger(name=__name__)
tracer = trace.get_tracer(__name__)

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
    """Make an HTTP POST request with retries, optional circuit breaker and distributed tracing.

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
    ERRORS = (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)

    if circuit_breaker and not circuit_breaker.can_execute():
        # Don't attempt if circuit is open
        raise CircuitOpenError(
            details=f"Circuit breaker is {CircuitBreakerStateEnum.OPEN.name}. Request blocked."
        )

    # Create a parent span for the retriable request
    with tracer.start_as_current_span("http.retriable_request") as parent_span:
        parent_span.set_attribute("http.url", url)
        parent_span.set_attribute("http.max_attempts", max_attempts)
        parent_span.set_attribute("http.method", "POST")

        last_exception: Exception | None = None
        last_response: httpx.Response | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(
                    multiplier=multiplier, min=min_wait, max=max_wait
                ),
                retry=retry_if_exception_type(
                    ERRORS + (httpx.HTTPStatusError,),  # 5xx errors (StatusError)
                ),
                reraise=True,
            ):
                with attempt:
                    with tracer.start_as_current_span(
                        f"http.attempt_{attempt.retry_state.attempt_number}"
                    ) as attempt_span:
                        attempt_span.set_attribute(
                            "http.attempt_number", attempt.retry_state.attempt_number
                        )

                        try:
                            # 5xx errors are retriable while 4xx are not
                            response = await client.post(url, json=payload)
                            attempt_span.set_attribute(
                                "http.status_code", response.status_code
                            )
                            last_response = response

                            # Successful response
                            if 200 <= response.status_code < 300:
                                if circuit_breaker:
                                    circuit_breaker.record_success()
                                attempt_span.set_status(Status(StatusCode.OK))
                                parent_span.set_status(Status(StatusCode.OK))
                                parent_span.add_event(
                                    "request_succeeded",
                                    {
                                        "attempt": attempt.retry_state.attempt_number,
                                        "status_code": response.status_code,
                                    },
                                )
                                return response

                            # Server error
                            if 500 <= response.status_code < 600:
                                if circuit_breaker:
                                    circuit_breaker.record_failure()
                                attempt_span.set_status(
                                    Status(StatusCode.ERROR, "Server error")
                                )
                                parent_span.set_status(
                                    Status(StatusCode.ERROR, "Server error")
                                )
                                parent_span.add_event(
                                    "request_failed",
                                    {
                                        "attempt": attempt.retry_state.attempt_number,
                                        "status_code": response.status_code,
                                    },
                                )
                                # Raise for retry
                                raise httpx.HTTPStatusError(
                                    f"Server error: {response.status_code}",
                                    request=response.request,
                                    response=response,
                                )

                            # Client error (4xx). Do not retry
                            if circuit_breaker:
                                circuit_breaker.record_failure()
                            attempt_span.set_status(
                                Status(StatusCode.ERROR, "Client error")
                            )
                            parent_span.add_event(
                                "request_failed",
                                {
                                    "attempt": attempt.retry_state.attempt_number,
                                    "status_code": response.status_code,
                                },
                            )

                            # No retry for 4xx errors
                            return response

                        except ERRORS as e:
                            if circuit_breaker:
                                circuit_breaker.record_failure()
                            logger.error(
                                f"All retry attempts failed for request to {url}: {e}"
                            )
                            parent_span.record_exception(e)
                            parent_span.set_status(Status(StatusCode.ERROR, str(e)))
                            attempt_span.add_event(
                                "network_error",
                                {
                                    "error_type": type(e).__name__,
                                    "attempt": attempt.retry_state.attempt_number,
                                },
                            )

                            last_exception = e
                            if attempt.retry_state.attempt_number < max_attempts:
                                wait_time = min(
                                    min_wait
                                    * (
                                        multiplier
                                        ** (attempt.retry_state.attempt_number - 1)
                                    ),
                                    max_wait,
                                )
                                logger.warning(
                                    f"Request failed (attempt f"
                                    "{attempt.retry_state.attempt_number}/{max_attempts}): "
                                    f"{type(e).__name__}. Retrying in {wait_time:.2f}s..."
                                )
                                attempt_span.add_event(
                                    "retrying",
                                    {
                                        "wait_seconds": wait_time,
                                        "next_attempt": attempt.retry_state.attempt_number
                                        + 1,
                                    },
                                )

                            # Re-raise to trigger retry
                            raise

        except Exception:  # noqa: S110
            # All attempts exhausted
            pass

        # After exhausting all attempts
        parent_span.set_status(Status(StatusCode.ERROR, "All retry attempts failed"))
        parent_span.add_event("max_attempts_reached", {"total_attempts": max_attempts})

        if last_exception:
            parent_span.record_exception(last_exception)
            logger.error(
                f"Final failure after {max_attempts} attempts for request to {url}: {last_exception}"
            )

        else:
            logger.error(
                f"Final failure after {max_attempts} attempts for request to {url}. "
                f"Last response: {last_response}"
            )

        return None


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
