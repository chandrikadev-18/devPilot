"""
DevPilot Observability & Request Correlation Middleware (v3.5 Enterprise).

Intercepts all HTTP requests to propagate X-Request-ID headers, track latency metrics,
and log structured audit entries without blocking.
"""

import time
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logger import logger
from app.observability.correlation import clear_request_id, get_request_id, set_request_id
from app.observability.metrics import metrics


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette middleware for request correlation, latency measurement,
    metrics recording, and structured access logging.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Extract or generate Request Correlation ID
        incoming_rid = request.headers.get("X-Request-ID") or request.headers.get("x-correlation-id")
        request_id = set_request_id(incoming_rid)

        metrics.record_request_start()
        start_time = time.time()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            status_code = 500
            metrics.record_error(exc.__class__.__name__)
            logger.error(
                f"Unhandled exception during HTTP request {request.method} {request.url.path}: {exc}",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
                exc_info=True,
            )
            from starlette.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                headers={
                    "X-Request-ID": request_id,
                    "X-Response-Time-MS": f"{(time.time() - start_time) * 1000.0:.2f}",
                },
                content={
                    "status": "error",
                    "request_id": request_id,
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected internal server error occurred.",
                    },
                    "detail": "An unexpected internal server error occurred.",
                },
            )
            return response
        finally:
            duration_ms = (time.time() - start_time) * 1000.0
            metrics.record_request_end(request.method, status_code, duration_ms)

            # Access Log (excluding noisy root health pings if healthy to reduce log spam)
            extra = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            }
            if status_code >= 500:
                logger.error(f"{request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)", extra=extra)
            elif status_code >= 400:
                logger.warning(f"{request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)", extra=extra)
            else:
                logger.info(f"{request.method} {request.url.path} -> {status_code} ({duration_ms:.2f}ms)", extra=extra)

            clear_request_id()

            # Ensure correlation and security headers are present if response object was created
            if "response" in locals() and isinstance(response, Response):
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["X-XSS-Protection"] = "1; mode=block"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

