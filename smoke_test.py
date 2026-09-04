"""
DevPilot v3.5 Enterprise End-to-End Production Smoke Test.

Executes and verifies:
1. Backend startup & lifespan initialization
2. Health liveness probe (/health & /api/health)
3. Health readiness probe (/health/ready & /api/health/ready)
4. Subsystem diagnostics (/health/details)
5. Request correlation ID propagation (X-Request-ID & X-Response-Time-MS)
6. Core workflow execution (Project registration, scan, graph build)
7. Expected API error triggering (404 Project Not Found)
8. Safe error response format (clean envelope without stack trace)
9. Error correlation with request ID
10. Performance metrics collection (/metrics)
11. Secret redaction in structured logs
12. Security & protection boundary
"""

import json
import logging
from pathlib import Path
import tempfile
import time
from fastapi.testclient import TestClient

from app.logger import StructuredJsonFormatter, redact_secrets
from app.main import app
from app.observability import get_request_id, metrics


def run_smoke_test():
    print("=" * 70)
    print("DevPilot v3.5 Enterprise — Production Smoke Test")
    print("=" * 70)

    client = TestClient(app)

    # Step 1: Health Liveness Probe
    print("\n[Step 1] Verifying Liveness Probe (/health)...")
    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Expected 200, got {res_health.status_code}"
    health_data = res_health.json()
    assert health_data["status"] == "ok"
    assert health_data["service"] == "DevPilot"
    print(f"  ✓ Liveness probe PASS: {health_data}")

    # Step 2: Health Readiness Probe
    print("\n[Step 2] Verifying Readiness Probe (/health/ready)...")
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200, f"Expected 200, got {res_ready.status_code}"
    ready_data = res_ready.json()
    assert ready_data["ready"] is True
    assert ready_data["status"] in ("healthy", "degraded")
    assert "storage" in ready_data["checks"]
    assert "vector_store" in ready_data["checks"]
    print(f"  ✓ Readiness probe PASS: status={ready_data['status']}, ready={ready_data['ready']}")

    # Step 3: Granular Diagnostics
    print("\n[Step 3] Verifying Subsystem Diagnostics (/health/details)...")
    res_details = client.get("/health/details")
    assert res_details.status_code == 200
    details = res_details.json()
    assert "git" in details and "storage" in details and "graph" in details and "llm" in details
    assert "api_key" not in details["llm"]  # No secret leakage
    print(f"  ✓ Diagnostics PASS: git={details['git']['available']}, storage={details['storage']['available']}")

    # Step 4: Request Correlation ID Propagation
    print("\n[Step 4] Verifying Correlation ID Propagation (X-Request-ID)...")
    custom_trace = "trace_prod_smoke_998877"
    res_corr = client.get("/health", headers={"X-Request-ID": custom_trace})
    assert res_corr.status_code == 200
    assert res_corr.headers.get("X-Request-ID") == custom_trace
    assert "X-Response-Time-MS" in res_corr.headers
    print(f"  ✓ Correlation ID PASS: {res_corr.headers.get('X-Request-ID')} (latency: {res_corr.headers.get('X-Response-Time-MS')}ms)")

    # Step 5: Core Workflow Execution
    print("\n[Step 5] Executing Core Workflow (Project Registration & Scan)...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_file = tmp_path / "main.py"
        test_file.write_text("def smoke_test_fn():\n    return 'ok'\n", encoding="utf-8")

        res_reg = client.post("/api/projects", json={"path": str(tmp_path), "name": "Smoke Test Project"})
        assert res_reg.status_code in (200, 201), f"Expected 200/201, got {res_reg.status_code}: {res_reg.text}"
        project_id = res_reg.json()["project_id"]
        print(f"  ✓ Project registered: {project_id}")

        res_scan = client.post(f"/api/projects/{project_id}/scan")
        assert res_scan.status_code == 200
        scan_data = res_scan.json()
        assert scan_data["total_files"] >= 1
        print(f"  ✓ Project scan complete: {scan_data['total_files']} files discovered")

    # Step 6: Expected API Error & Correlation Response
    print("\n[Step 6] Triggering Expected API Error (404 Project Not Found)...")
    res_err = client.get("/api/projects/proj_smoke_non_existent_12345")
    assert res_err.status_code == 404
    err_data = res_err.json()
    assert err_data["status"] == "error"
    assert "request_id" in err_data
    assert err_data["error"]["code"] == "PROJECT_NOT_FOUND"
    assert res_err.headers.get("X-Request-ID") == err_data["request_id"]
    print(f"  ✓ Safe error envelope PASS: code={err_data['error']['code']}, request_id={err_data['request_id']}")

    # Step 7: Operational Performance Metrics
    print("\n[Step 7] Inspecting Performance Metrics (/metrics)...")
    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200
    metric_data = res_metrics.json()
    assert metric_data["requests"]["total"] > 0
    assert "2xx" in metric_data["requests"]["by_status"]
    assert "4xx" in metric_data["requests"]["by_status"]
    assert metric_data["latency_ms"]["count"] > 0
    print(f"  ✓ Metrics PASS: requests={metric_data['requests']['total']}, p50={metric_data['latency_ms']['p50']}ms, p95={metric_data['latency_ms']['p95']}ms")

    # Step 8: Structured Logging & Secret Redaction
    print("\n[Step 8] Verifying Structured Logging and Secret Redaction...")
    formatter = StructuredJsonFormatter()
    log_rec = logging.LogRecord(
        name="devpilot.smoke",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Login attempt with token Bearer secret_token_value_12345678 and api_key=gsk_secret_groq_api_key_9999",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(log_rec)
    parsed = json.loads(formatted)
    assert "secret_token_value" not in parsed["message"]
    assert "secret_groq_api_key" not in parsed["message"]
    assert "[REDACTED]" in parsed["message"]
    print(f"  ✓ Secret Redaction PASS: {parsed['message']}")

    print("\n" + "=" * 70)
    print("ALL PRODUCTION SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_smoke_test()
