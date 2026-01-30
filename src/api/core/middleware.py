"""Custom middleware for request ID assignment, logging, error handling, and credit deduction."""

import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, Response, status
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from src import create_logger
from src.api.core.auth import adeduct_credits_background
from src.api.core.exceptions import (
    CircuitOpenError,
    HTTPError,
    RateLimitError,
    ServiceUnavailableError,
    UnauthorizedError,
    UnexpectedError,
)
from src.api.core.responses import MsgSpecJSONResponse
from src.schemas.types import ErrorCodeEnum
from src.utilities.utils import msgspec_encoder

logger = create_logger(name=__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add a unique request ID to each incoming request.
    The request ID is used for tracing and logging purposes.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Add a unique request ID to the request and response headers."""
        # Check for existing request ID from client
        client_req_id: str | None = request.headers.get("X-Request-ID", None)

        if client_req_id and len(client_req_id) <= 128:
            request_id = client_req_id.strip()
        else:
            # Generate a new UUID if not provided or invalid
            request_id = str(uuid4())

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log incoming requests and outgoing responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Log request and response details."""
        start_time: float = time.perf_counter()

        request_id = getattr(request.state, "request_id", "N/A")
        response: Response = await call_next(request)
        # in milliseconds
        process_time: float = round(((time.perf_counter() - start_time) * 1000), 2)
        response.headers["X-Process-Time-MS"] = str(process_time)

        log: dict[str, Any] = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time_ms": process_time,
            "request_id": request_id,
        }

        # Use msgspec for optimized serialization
        logger.info(msgspec_encoder.encode(log).decode("utf-8"))

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware to handle exceptions and return standardized error responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Catch exceptions and return standardized error responses."""
        try:
            response: Response = await call_next(request)
            return response

        except (HTTPError, HTTPException) as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {
                        "message": exc.message
                        if hasattr(exc, "message")
                        else (exc.detail if hasattr(exc, "detail") else "HTTP error"),
                        "code": ErrorCodeEnum.HTTP_ERROR,
                    },
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )

        except UnauthorizedError as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {"message": exc.message, "code": exc.error_code},
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )

        except CircuitOpenError as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {"message": exc.message, "code": exc.error_code},
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )
        except RateLimitError as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {"message": exc.message, "code": exc.error_code},
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )
        except ServiceUnavailableError as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {"message": exc.message, "code": exc.error_code},
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )

        except UnexpectedError as exc:
            return MsgSpecJSONResponse(
                status_code=exc.status_code,
                content={
                    "status": "error",
                    "error": {"message": exc.message, "code": exc.error_code},
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )

        except Exception as exc:
            logger.exception(f"Unhandled exception in middleware: {exc}")
            return MsgSpecJSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "status": "error",
                    "error": {
                        "message": "An unexpected server error occurred.",
                        "code": ErrorCodeEnum.UNEXPECTED_ERROR,
                    },
                    "request_id": getattr(request.state, "request_id", "N/A"),
                    "path": str(request.url.path),
                },
                headers=getattr(exc, "headers", None),
            )


class CreditDeductionMiddleware(BaseHTTPMiddleware):
    """Middleware to deduct credits from API key clients on successful responses.

    Only deducts credits if the response status code is < 400 (successful).
    This prevents charging users for failed requests.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Deduct credits from client after successful response."""
        response: Response = await call_next(request)

        # Quick check to see if we need to deduct credits
        if response.status_code < 400 and hasattr(request.state, "api_key_client_id"):
            client_id = request.state.api_key_client_id
            cost = request.state.api_key_cost

            client_id = request.state.api_key_client_id
            cost = request.state.api_key_cost

            # Add the task to the response
            # FastAPI/Starlette will execute this AFTER sending bytes to the client
            response.background = BackgroundTask(
                adeduct_credits_background, client_id=client_id, cost=cost
            )

        return response


# ===== Define the stack of middleware =====
# REQUEST FLOW:
# RequestIDMiddleware (Outermost) -> LoggingMiddleware
# -> ErrorHandlingMiddleware -> CreditDeductionMiddleware -> [Endpoint]
#
# RESPONSE FLOW:
# [Endpoint] -> CreditDeductionMiddleware -> ErrorHandlingMiddleware
# -> LoggingMiddleware -> RequestIDMiddleware (Outermost)
MIDDLEWARE_STACK: list[type[BaseHTTPMiddleware]] = [
    RequestIDMiddleware,  # 1. Touches request first
    LoggingMiddleware,  # 2. Touches request second
    ErrorHandlingMiddleware,  # 3. Touches request third
    CreditDeductionMiddleware,  # 4. Touches request fourth (closest to route, deducts on response)
]
# Reverse the middleware stack to maintain the correct order! (LIFO: Last In, First Out for requests)
MIDDLEWARE_STACK.reverse()
