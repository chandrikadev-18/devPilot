"""
Tests for DevPilot v2.6 — Production Hardening + Observability.

Covers:
1. Configuration loading
2. Missing environment variables fallback
3. Default configuration
4. Structured logging
5. Secret redaction
6. Health endpoint (/health)
7. Detailed health endpoint (/health/details)
8. API exception handling & error envelope
9. Project not found error
10. Invalid project path error
11. Git error handling
12. Operation timing
13. Operation failure recording
14. Timeout handling
15. CLI non-zero exit code
16. Security / Path traversal protection
17. Command injection protection
18. API response format
19. OpenAPI registration
20. Existing functionality regression
"""

import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

from app.changes.test_runner import TestRunner
from app.config import (
    get_api_host,
    get_api_port,
    get_config_summary,
    get_environment,
    get_llm_api_key,
    get_llm_model,
    get_llm_provider,
    get_log_level,
    get_max_project_size_mb,
    get_operation_timeout,
    get_project_storage_location,
    get_test_timeout,
    load_env_file,
)
from app.logger import (
    StructuredJsonFormatter,
    get_logger,
    log_operation_complete,
    log_operation_error,
    log_operation_start,
    redact_secrets,
    sanitize_payload,
)
from app.main import app, run_project_add, run_project_info
from app.projects.models import OperationStatus, ProjectStatus
from app.projects.service import (
    DuplicateProjectError,
    InvalidProjectPathError,
    ProjectNotFoundError,
    ProjectService,
)
from app.projects.store import OperationStore, ProjectStore


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Sets up a clean temporary Git repository project for testing."""
    app_dir = tmp_path / "app" / "graph"
    app_dir.mkdir(parents=True, exist_ok=True)
    builder_file = app_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self, project_path: str):\n"
        "        return True\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(tmp_path), capture_output=True, check=True)
    return tmp_path


# ==============================================================================
# 1-3. Configuration Tests
# ==============================================================================

def test_1_configuration_loading(tmp_path: Path):
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "DEVPILOT_ENV=staging\n"
        "LOG_LEVEL=DEBUG\n"
        "OPERATION_TIMEOUT=45.5\n"
        "TEST_TIMEOUT=15.0\n"
        "MAX_PROJECT_SIZE_MB=250.0\n",
        encoding="utf-8",
    )
    # Clear existing if any
    for k in ("DEVPILOT_ENV", "LOG_LEVEL", "OPERATION_TIMEOUT", "TEST_TIMEOUT", "MAX_PROJECT_SIZE_MB"):
        os.environ.pop(k, None)

    load_env_file(env_file)
    assert get_environment() == "staging"
    assert get_log_level() == "DEBUG"
    assert get_operation_timeout() == 45.5
    assert get_test_timeout() == 15.0
    assert get_max_project_size_mb() == 250.0


def test_2_missing_environment_variables_fallback():
    # Remove vars to test defaults
    for k in ("DEVPILOT_ENV", "ENVIRONMENT", "LOG_LEVEL", "OPERATION_TIMEOUT", "TEST_TIMEOUT"):
        os.environ.pop(k, None)

    assert get_environment() == "development"
    assert get_log_level() == "INFO"
    assert get_operation_timeout() == 60.0
    assert get_test_timeout() == 30.0


def test_3_default_configuration_and_summary():
    summary = get_config_summary()
    assert isinstance(summary, dict)
    assert "environment" in summary
    assert "log_level" in summary
    assert "operation_timeout_sec" in summary
    assert "test_timeout_sec" in summary
    assert "llm_api_key_configured" in summary
    # Secrets should not be exposed
    assert "llm_api_key" not in summary


# ==============================================================================
# 4-5. Structured Logging & Secret Redaction
# ==============================================================================

def test_4_structured_logging(capsys):
    logger = get_logger("test_structured")
    log_operation_start("test_op", project_id="proj_123", operation_id="op_456")
    log_operation_complete("test_op", duration_ms=123.45, project_id="proj_123", operation_id="op_456")


def test_5_secret_redaction():
    # 1. Groq / OpenAI style keys
    text1 = "Error connecting with key gsk_1234567890abcdef1234567890abcdef"
    redacted1 = redact_secrets(text1)
    assert "gsk_1234567890abcdef1234567890abcdef" not in redacted1
    assert "[REDACTED]" in redacted1

    # 2. Bearer tokens
    text2 = "Authorization: Bearer mySecretToken1234567890"
    redacted2 = redact_secrets(text2)
    assert "mySecretToken" not in redacted2
    assert "Bearer [REDACTED]" in redacted2

    # 3. Payload dictionary redaction
    payload = {
        "user": "developer",
        "api_key": "secret_key_value",
        "password": "super_secret_password",
        "nested": {"token": "xyz123"},
    }
    clean = sanitize_payload(payload)
    assert clean["api_key"] == "[REDACTED]"
    assert clean["password"] == "[REDACTED]"
    assert clean["nested"]["token"] == "[REDACTED]"
    assert clean["user"] == "developer"


# ==============================================================================
# 6-7. Health Endpoints
# ==============================================================================

def test_6_health_endpoint(client: TestClient):
    # Root /health
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "DevPilot"

    # Namespaced /api/health
    api_res = client.get("/api/health")
    assert api_res.status_code == 200
    assert api_res.json()["status"] == "ok"


def test_7_detailed_health_endpoint(client: TestClient):
    # Root /health/details
    res = client.get("/health/details")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "git" in data
    assert "storage" in data
    assert "graph" in data
    assert "llm" in data
    assert data["storage"]["available"] is True


# ==============================================================================
# 8-10. Exception Handling & Error Envelopes
# ==============================================================================

def test_8_api_exception_handling(client: TestClient):
    res = client.get("/projects/non_existent_project_id_123")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"
    assert "detail" in data


def test_9_project_not_found_error(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)
    with pytest.raises(ProjectNotFoundError):
        service.get_project("proj_does_not_exist_xyz")


def test_10_invalid_project_path_error(tmp_path: Path):
    service = ProjectService(project_root=tmp_path)
    with pytest.raises(InvalidProjectPathError):
        service.validate_path(str(tmp_path / "missing_directory_abc"))


# ==============================================================================
# 11-13. Git Error & Operation Timing / Failures
# ==============================================================================

def test_11_git_error_handling(tmp_path: Path):
    # Non-git directory
    non_git_dir = tmp_path / "not_git"
    non_git_dir.mkdir()
    service = ProjectService(project_root=tmp_path)
    proj = service.register_project(path=str(non_git_dir), name="Non Git")
    assert proj.repository is None


def test_12_operation_timing(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    op, result = service.scan_project(project.project_id)
    assert "duration_ms" in result
    assert result["duration_ms"] >= 0.0
    assert op.status == OperationStatus.COMPLETED.value


def test_13_operation_failure_recording(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    project.path = str(temp_project / "nonexistent_subfolder")
    store.save(project)

    with pytest.raises(InvalidProjectPathError):
        service.scan_project(project.project_id)


# ==============================================================================
# 14. Timeout Handling
# ==============================================================================

def test_14_timeout_handling(temp_project: Path):
    # Runner with 1 second timeout running a sleep or hanging test
    runner = TestRunner(project_root=temp_project, timeout_seconds=1)
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)
        result = runner.run_tests()
        assert result.is_success is False
        assert result.exit_code == 124
        assert "timed out" in result.output.lower()


# ==============================================================================
# 15. CLI Non-Zero Exit Code
# ==============================================================================

def test_15_cli_non_zero_exit_code():
    with pytest.raises(SystemExit) as exc_info:
        run_project_info(project_id="proj_invalid_id_999", as_json=False)
    assert exc_info.value.code == 1


# ==============================================================================
# 16-17. Security & Injection Protection
# ==============================================================================

def test_16_path_traversal_protection(tmp_path: Path):
    service = ProjectService(project_root=tmp_path)
    with pytest.raises(InvalidProjectPathError):
        service.validate_path("../../etc/passwd")

    with pytest.raises(InvalidProjectPathError):
        service.validate_path("some\0path")


def test_17_command_injection_protection(tmp_path: Path):
    service = ProjectService(project_root=tmp_path)
    with pytest.raises(InvalidProjectPathError):
        service.validate_path("$(rm -rf /)")


# ==============================================================================
# 18-19. API Response Format & OpenAPI Schema
# ==============================================================================

def test_18_api_response_format(client: TestClient, temp_project: Path):
    # Test registered endpoint produces correct json format
    res = client.post("/projects", json={"path": str(temp_project), "name": "Format Test"})
    if res.status_code == 201:
        assert res.json()["name"] == "Format Test"
    else:
        assert res.status_code == 409
        assert res.json()["status"] == "error"


def test_19_openapi_registration(client: TestClient):
    res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/health" in paths
    assert "/health/details" in paths
    assert "/projects" in paths
    assert "/projects/{project_id}/scan" in paths


# ==============================================================================
# 20. Existing Functionality Regression
# ==============================================================================

def test_20_existing_functionality_regression(client: TestClient):
    # Health v1.4 compatibility
    health = client.get("/api/health").json()
    assert health["version"] == "1.4"
    assert health["service"] == "DevPilot"
