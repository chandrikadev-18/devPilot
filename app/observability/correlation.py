"""
DevPilot Request Correlation & Context Propagation Module (v3.5 Enterprise).

Provides async-safe ContextVar storage for request correlation IDs (X-Request-ID)
across logging, service layers, and background operations.
"""

from contextvars import ContextVar
import uuid
from typing import Optional

# Global context variable for request correlation ID
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("devpilot_request_id", default=None)


def get_request_id() -> str:
    """
    Returns the current request correlation ID, or a default 'system' identifier
    if called outside an HTTP request context.
    """
    req_id = _request_id_ctx.get()
    return req_id or "sys_background"


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Sets the request correlation ID for the current async context.
    If no ID is supplied, generates a clean UUID4 identifier.
    """
    rid = request_id.strip() if request_id and request_id.strip() else f"req_{uuid.uuid4().hex[:12]}"
    _request_id_ctx.set(rid)
    return rid


def clear_request_id() -> None:
    """Clears the request ID from the current context."""
    _request_id_ctx.set(None)
