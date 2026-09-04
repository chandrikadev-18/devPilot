"""
DevPilot Enterprise Observability Package (v3.5).

Exposes request correlation, performance metrics, and observability middleware.
"""

from app.observability.correlation import clear_request_id, get_request_id, set_request_id
from app.observability.metrics import MetricsCollector, metrics
from app.observability.middleware import ObservabilityMiddleware

__all__ = [
    "get_request_id",
    "set_request_id",
    "clear_request_id",
    "MetricsCollector",
    "metrics",
    "ObservabilityMiddleware",
]
