"""
DevPilot Operational Performance Metrics Collector (v3.5 Enterprise).

Provides lightweight, thread-safe in-memory metric aggregation for requests,
latencies, error distributions, task lifecycles, and database operations.
"""

from collections import defaultdict
from datetime import datetime, timezone
import math
import threading
import time
from typing import Any, Dict, List, Optional


class MetricsCollector:
    """Thread-safe operational performance metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._start_datetime = datetime.now(timezone.utc).isoformat()
        self._requests_total: int = 0
        self._requests_by_method: Dict[str, int] = defaultdict(int)
        self._requests_by_status: Dict[str, int] = defaultdict(int)
        self._active_requests: int = 0
        self._latencies_ms: List[float] = []
        self._errors_total: Dict[str, int] = defaultdict(int)
        self._task_executions: Dict[str, int] = defaultdict(int)
        self._db_operations: Dict[str, int] = defaultdict(int)

    def record_request_start(self) -> None:
        """Increments active request count."""
        with self._lock:
            self._active_requests += 1

    def record_request_end(
        self,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Records completed HTTP request metrics."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._requests_total += 1
            self._requests_by_method[method.upper()] += 1

            status_group = f"{status_code // 100}xx"
            self._requests_by_status[status_group] += 1
            self._requests_by_status[str(status_code)] += 1

            # Store bounded window of recent latencies (last 2,000 requests)
            self._latencies_ms.append(duration_ms)
            if len(self._latencies_ms) > 2000:
                self._latencies_ms.pop(0)

    def record_error(self, error_code: str) -> None:
        """Records an error occurrence by error code category."""
        with self._lock:
            self._errors_total[error_code] += 1

    def record_task_execution(self, status: str) -> None:
        """Records an issue-to-PR task lifecycle transition/execution."""
        with self._lock:
            self._task_executions[status.upper()] += 1

    def record_db_operation(self, operation: str, success: bool = True) -> None:
        """Records a database or storage persistence operation."""
        with self._lock:
            key = f"{operation}:{'success' if success else 'failed'}"
            self._db_operations[key] += 1

    def get_summary(self) -> Dict[str, Any]:
        """Returns structured metrics summary."""
        with self._lock:
            uptime = round(time.time() - self._start_time, 2)
            latencies = list(self._latencies_ms)

            avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            min_latency = round(min(latencies), 2) if latencies else 0.0
            max_latency = round(max(latencies), 2) if latencies else 0.0

            # Calculate p50 and p95
            if latencies:
                sorted_lats = sorted(latencies)
                p50_idx = max(0, int(math.ceil(0.50 * len(sorted_lats))) - 1)
                p95_idx = max(0, int(math.ceil(0.95 * len(sorted_lats))) - 1)
                p50_latency = round(sorted_lats[p50_idx], 2)
                p95_latency = round(sorted_lats[p95_idx], 2)
            else:
                p50_latency = 0.0
                p95_latency = 0.0

            return {
                "service": "DevPilot",
                "uptime_seconds": uptime,
                "started_at": self._start_datetime,
                "requests": {
                    "total": self._requests_total,
                    "active": self._active_requests,
                    "by_method": dict(self._requests_by_method),
                    "by_status": dict(self._requests_by_status),
                },
                "latency_ms": {
                    "count": len(latencies),
                    "min": min_latency,
                    "avg": avg_latency,
                    "p50": p50_latency,
                    "p95": p95_latency,
                    "max": max_latency,
                },
                "errors": dict(self._errors_total),
                "tasks": dict(self._task_executions),
                "database_operations": dict(self._db_operations),
            }


# Singleton global metrics collector instance
metrics = MetricsCollector()
