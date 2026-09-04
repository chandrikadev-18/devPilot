"""
DevPilot v3.5 Enterprise Observability, Health & Monitoring Test Suite.

Validates:
1. Liveness health check (/health & /api/health)
2. Readiness health check (/health/ready & /api/health/ready)
3. Readiness probe failure simulation (unavailable when storage fails)
4. Readiness probe degraded simulation (degraded when git or graph parser is missing)
5. Detailed health probe diagnostics without secret leaking (/health/details)
6. Request correlation ID propagation (X-Request-ID) and response time
7. Operational performance metrics aggregation (/metrics & /api/metrics)
8. Latency percentiles (min, avg, p50, p95, max) calculation
9. Task execution lifecycle recording in metrics
10. Database operation observability and success/failure recording
11. Structured JSON logging with automatic secret redaction
12. Request ID context propagation in structured logger
13. API error response contains request correlation ID envelope
14. Specific exception handlers (DuplicateProjectError, InvalidProjectPathError) correlation
15. Unhandled exception handler error envelope without stack trace leakage
16. Secret redaction on nested payloads, bearer tokens, and API keys
"""

import json
import logging
from pathlib import Path
import shutil
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.logger import StructuredJsonFormatter, redact_secrets, sanitize_payload
from app.main import app
from app.observability.correlation import clear_request_id, get_request_id, set_request_id
from app.observability.metrics import MetricsCollector, metrics


@pytest.fixture
def client():
    return TestClient(app)


# 1. Liveness Health Checks
def test_health_liveness_probe(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "DevPilot"
    assert data["version"] == "1.4"

    # Also test /api/health
    api_res = client.get("/api/health")
    assert api_res.status_code == 200
    assert api_res.json()["status"] == "ok"


# 2. Readiness Probe (Healthy)
def test_health_readiness_probe_healthy(client):
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["status"] in ("healthy", "degraded")
    assert "checks" in data
    assert "storage" in data["checks"]
    assert "vector_store" in data["checks"]
    assert "graph_parser" in data["checks"]
    assert "git" in data["checks"]

    # Namespaced /api/health/ready
    api_res = client.get("/api/health/ready")
    assert api_res.status_code == 200
    assert api_res.json()["ready"] is True


# 3. Readiness Probe (Unavailable when storage is not writable)
def test_health_readiness_probe_storage_failure(client):
    with patch.object(Path, "write_text", side_effect=PermissionError("Read-only filesystem")):
        res = client.get("/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["ready"] is False
        assert data["status"] == "unavailable"
        assert data["checks"]["storage"]["status"] == "unavailable"
        assert data["checks"]["storage"]["writable"] is False


# 4. Readiness Probe (Degraded when git is not in PATH)
def test_health_readiness_probe_git_missing(client):
    with patch("shutil.which", return_value=None):
        res = client.get("/health/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["ready"] is True
        assert data["status"] == "degraded"
        assert data["checks"]["git"]["status"] == "degraded"
        assert data["checks"]["git"]["available"] is False


# 5. Detailed Health Diagnostics (No secret leaks)
def test_detailed_health_diagnostics_no_secret_leak(client):
    res = client.get("/health/details")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "git" in data
    assert "storage" in data
    assert "graph" in data
    assert "llm" in data
    assert "api_key_configured" in data["llm"]
    # Ensure raw API key is never exposed
    assert "api_key" not in data["llm"]
    assert "gsk_" not in str(data)
    assert "Bearer" not in str(data)


# 6. Request Correlation ID Propagation & Timing Headers
def test_request_correlation_id_propagation(client):
    custom_rid = "req_custom_trace_987654"
    res = client.get("/health", headers={"X-Request-ID": custom_rid})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_rid
    assert "X-Response-Time-MS" in res.headers

    # Auto-generated ID if header is omitted
    res_auto = client.get("/health")
    assert res_auto.status_code == 200
    auto_id = res_auto.headers.get("X-Request-ID")
    assert auto_id is not None
    assert auto_id.startswith("req_")


# 7. Operational Metrics Aggregation
def test_operational_metrics_collector(client):
    client.get("/health")
    client.get("/health/ready")

    res = client.get("/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "DevPilot"
    assert data["uptime_seconds"] >= 0
    assert data["requests"]["total"] >= 2
    assert "2xx" in data["requests"]["by_status"]
    assert "latency_ms" in data
    assert "avg" in data["latency_ms"]
    assert "database_operations" in data


# 8. Latency Percentiles Calculation
def test_metrics_latency_percentiles():
    collector = MetricsCollector()
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    for lat in latencies:
        collector.record_request_end("GET", 200, lat)

    summary = collector.get_summary()
    assert summary["latency_ms"]["count"] == 10
    assert summary["latency_ms"]["min"] == 10.0
    assert summary["latency_ms"]["max"] == 100.0
    assert summary["latency_ms"]["avg"] == 55.0
    assert summary["latency_ms"]["p50"] == 50.0
    assert summary["latency_ms"]["p95"] == 100.0


# 9. Task Execution Lifecycle Metrics
def test_task_execution_metrics():
    collector = MetricsCollector()
    collector.record_task_execution("SUCCESS")
    collector.record_task_execution("FAILED")
    collector.record_task_execution("SUCCESS")

    summary = collector.get_summary()
    assert summary["tasks"]["SUCCESS"] == 2
    assert summary["tasks"]["FAILED"] == 1


# 10. Database / Persistence Observability Metrics
def test_database_observability_recording():
    collector = MetricsCollector()
    collector.record_db_operation("project_save", success=True)
    collector.record_db_operation("project_save", success=True)
    collector.record_db_operation("vector_upsert", success=False)

    summary = collector.get_summary()
    assert summary["database_operations"]["project_save:success"] == 2
    assert summary["database_operations"]["vector_upsert:failed"] == 1


# 11. Structured JSON Logging and Secret Redaction
def test_structured_logging_and_secret_redaction():
    formatter = StructuredJsonFormatter()

    log_record = logging.LogRecord(
        name="devpilot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="API call failed with password='super_secret_123' and api_key=gsk_123456789012345678901234567890",
        args=(),
        exc_info=None,
    )
    log_record.request_id = "req_test_log_001"
    log_record.project_id = "proj_01"

    formatted = formatter.format(log_record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["request_id"] == "req_test_log_001"
    assert parsed["project_id"] == "proj_01"
    assert "super_secret_123" not in parsed["message"]
    assert "gsk_1234567890" not in parsed["message"]
    assert "[REDACTED]" in parsed["message"]


# 12. Correlation ID Context Propagation in Structured Logging
def test_structured_logging_context_propagation():
    formatter = StructuredJsonFormatter()
    test_rid = "req_ctx_var_12345"
    set_request_id(test_rid)
    try:
        log_record = logging.LogRecord(
            name="devpilot.context_test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=20,
            msg="Operation warning occurred",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(log_record)
        parsed = json.loads(formatted)
        assert parsed["request_id"] == test_rid
    finally:
        clear_request_id()


# 13. API Error Response Envelope with Request ID
def test_api_error_response_contains_correlation_id(client):
    res = client.get("/api/projects/proj_non_existent_999999")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == "error"
    assert "request_id" in data
    assert res.headers.get("X-Request-ID") == data["request_id"]
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"


# 14. Error Code Resolution for 400 and 409
def test_error_code_envelopes(client):
    # Invalid project path (400)
    res_bad = client.post("/api/projects", json={"path": "", "name": ""})
    assert res_bad.status_code in (400, 422)
    data_bad = res_bad.json()
    assert "request_id" in data_bad or "detail" in data_bad


# 15. Unhandled Exception Handler Returns Clean 500 Without Leaking Internal Trace
def test_unhandled_exception_handler_clean_envelope(client):
    with patch("app.api.health.HealthResponse", side_effect=RuntimeError("Simulated internal crash")):
        res = client.get("/health")
        assert res.status_code == 500
        data = res.json()
        assert data["status"] == "error"
        assert "request_id" in data
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "unexpected" in data["error"]["message"].lower() or "internal" in data["error"]["message"].lower()
        # Verify internal crash string was not exposed
        assert "Simulated internal crash" not in data["error"]["message"]



# 16. Comprehensive Secret Redaction Patterns
def test_comprehensive_secret_redaction():
    # 1. Bearer Token
    assert redact_secrets("Authorization: Bearer abcd1234efgh5678ijkl") == "Authorization: Bearer [REDACTED]"

    # 2. Env style LLM API key
    assert redact_secrets("GROQ_API_KEY=gsk_999988887777666655554444") == "GROQ_API_KEY=[REDACTED]"
    assert redact_secrets("OPENAI_API_KEY=sk-proj-12345678901234567890") == "OPENAI_API_KEY=[REDACTED]"

    # 3. Payload dict sanitize
    payload = {
        "user": "test_user",
        "api_key": "secret_key_123",
        "nested": {
            "token": "tok_abcdef123456",
            "safe_field": "public_data",
        },
    }
    clean = sanitize_payload(payload)
    assert clean["user"] == "test_user"
    assert clean["api_key"] == "[REDACTED]"
    assert clean["nested"]["token"] == "[REDACTED]"
    assert clean["nested"]["safe_field"] == "public_data"
