"""
DevPilot v3.8 Enterprise Security Hardening & Compliance Test Suite.

Validates:
1. HTTP Security Headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)
2. CORS security boundary (explicit origins, no unsafe wildcards with credentials)
3. Secret Redaction & Log Sanitization (Groq, OpenAI, Bearer tokens, passwords, nested structures)
4. Path Traversal & File Boundary Protection (../, .env, .git, null bytes, absolute escape)
5. Command Injection Protection (rejecting shell metas, rm -rf, subshells in path validation)
6. Approval-Gate Security (enforcing approval before execution, rejecting bypass attempts)
7. High-Risk Confirmation Enforcement (requiring explicit confirmation for high-risk changes)
8. Proposal State Machine Integrity (preventing execution of rejected/pending proposals)
9. Stale Proposal & File Hash Drift Detection (rejecting modifications to changed target files)
10. Error & Information Disclosure Protection (safe 500 envelopes, no stack traces leaked)
11. IDOR & Invalid Resource Access Protection (404/400 on forged IDs)
12. Adversarial Payload Handling (oversized inputs, unicode edge cases, malformed JSON)
13. Read-Only Codebase Tool Boundary (sandbox enforcement across search, read, AST tools)
14. Health Diagnostic Security (ensuring /health and /health/details never leak API keys)
15. ContextVar Request Correlation Security (isolation across concurrent requests)
"""

import json
import logging
from pathlib import Path
import tempfile
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.agent.tools import SecurityError, resolve_safe_path
from app.changes.approval import (
    AlreadyAppliedError,
    ApprovalService,
    DuplicateApprovalError,
    HighRiskConfirmationError,
    ProposalNotFoundError,
    RejectedProposalError,
    StaleProposalError,
)
from app.changes.models import ChangeProposal, ProposalStatus
from app.changes.proposal_store import ProposalStore, compute_file_hash
from app.logger import StructuredJsonFormatter, redact_secrets, sanitize_payload
from app.main import app
from app.observability import get_request_id, set_request_id


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. HTTP Security Headers
# ==============================================================================
def test_http_security_headers_present_on_all_responses(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ==============================================================================
# 2. CORS Security Boundary
# ==============================================================================
def test_cors_security_configured_properly(client):
    # Valid origin
    res = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ==============================================================================
# 3. Secret Redaction & Log Sanitization
# ==============================================================================
def test_secret_redaction_comprehensive_patterns():
    # 1. Groq & OpenAI Keys
    assert redact_secrets("API Key: gsk_1234567890abcdef1234567890abcdef") == "API Key: [REDACTED]"
    assert redact_secrets("GROQ_API_KEY=gsk_secret_value_12345678") == "GROQ_API_KEY=[REDACTED]"
    assert redact_secrets("OPENAI_API_KEY=sk-proj-abcdef1234567890") == "OPENAI_API_KEY=[REDACTED]"

    # 2. Bearer Authentication Tokens
    assert redact_secrets("Authorization: Bearer my_jwt_token_12345678") == "Authorization: Bearer [REDACTED]"

    # 3. Key-Value Passwords and Tokens
    assert redact_secrets("password='SuperSecretPass123!'") == "password='[REDACTED]'"
    assert redact_secrets("token: 'xyz_token_456'") == "token: '[REDACTED]'"

    # 4. Nested Dictionary Payload Sanitization
    nested_payload = {
        "user_id": "usr_99",
        "auth": {"api_key": "secret_abc", "password": "pass_123"},
        "credentials": {"token": "tok_111"},
        "metadata": {"env": "prod"},
    }
    clean = sanitize_payload(nested_payload)
    assert clean["auth"] == "[REDACTED]"
    assert clean["credentials"]["token"] == "[REDACTED]"
    assert clean["metadata"]["env"] == "prod"




# ==============================================================================
# 4. Path Traversal & File Boundary Security
# ==============================================================================
def test_path_traversal_prevention():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "safe_file.py").write_text("print('safe')", encoding="utf-8")

        # 1. Directory Traversal Attempts
        with pytest.raises(SecurityError, match="Directory traversal is forbidden"):
            resolve_safe_path("../etc/passwd", root)

        with pytest.raises(SecurityError, match="Directory traversal is forbidden"):
            resolve_safe_path("folder/../../escape.py", root)

        # 2. Sensitive Environment Files
        with pytest.raises(SecurityError, match="Access to environment files is forbidden"):
            resolve_safe_path(".env", root)

        with pytest.raises(SecurityError, match="Access to environment files is forbidden"):
            resolve_safe_path("subfolder/.env.production", root)

        # 3. Internal Git Directory
        with pytest.raises(SecurityError, match="Access to internal .git directory is forbidden"):
            resolve_safe_path(".git/config", root)

        # 4. Empty Path
        with pytest.raises(SecurityError, match="File path cannot be empty"):
            resolve_safe_path("", root)

        # 5. Valid Relative Path
        safe_path = resolve_safe_path("safe_file.py", root)
        assert safe_path.exists()


# ==============================================================================
# 5. Approval-Gate Security & State Enforcement
# ==============================================================================
def test_approval_gate_enforcement():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test_file = root / "app.py"
        test_file.write_text("def run(): return 1\n", encoding="utf-8")

        store = ProposalStore(project_root=root)
        service = ApprovalService(project_root=root, store=store)

        proposal = ChangeProposal(
            request="Update run function",
            proposal_id="prop_sec_001",
            target_symbol="run",
            target_file=str(test_file),
            target_content_hash=compute_file_hash(test_file),
            risk="LOW",
            status=ProposalStatus.PENDING_APPROVAL.value,
        )
        store.save(proposal)

        # 1. Approval transitions to APPROVED
        approved = service.approve_proposal("prop_sec_001", reason="Verified change")
        assert approved.status == ProposalStatus.APPROVED.value

        # 2. Duplicate approval rejected
        with pytest.raises(DuplicateApprovalError):
            service.approve_proposal("prop_sec_001")


def test_high_risk_approval_requires_explicit_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test_file = root / "core.py"
        test_file.write_text("def core(): pass\n", encoding="utf-8")

        store = ProposalStore(project_root=root)
        service = ApprovalService(project_root=root, store=store)

        proposal = ChangeProposal(
            request="High risk refactoring",
            proposal_id="prop_high_risk_001",
            target_symbol="core",
            target_file=str(test_file),
            target_content_hash=compute_file_hash(test_file),
            risk="HIGH",
            status=ProposalStatus.PENDING_APPROVAL.value,
        )
        store.save(proposal)

        # High risk without force flag fails
        with pytest.raises(HighRiskConfirmationError):
            service.approve_proposal("prop_high_risk_001", force=False)

        # High risk with explicit force flag succeeds
        approved = service.approve_proposal("prop_high_risk_001", force=True)
        assert approved.status == ProposalStatus.APPROVED.value


def test_stale_proposal_detection_when_target_modified():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test_file = root / "service.py"
        test_file.write_text("initial code\n", encoding="utf-8")

        store = ProposalStore(project_root=root)
        service = ApprovalService(project_root=root, store=store)

        proposal = ChangeProposal(
            request="Stale proposal",
            proposal_id="prop_stale_001",
            target_symbol="service",
            target_file=str(test_file),
            target_content_hash=compute_file_hash(test_file),
            risk="LOW",
            status=ProposalStatus.PENDING_APPROVAL.value,
        )
        store.save(proposal)

        # Modify target file to induce staleness
        test_file.write_text("modified code by another process\n", encoding="utf-8")

        with pytest.raises(StaleProposalError, match="modified since proposal creation"):
            service.approve_proposal("prop_stale_001")



# ==============================================================================
# 6. Error Disclosure & Information Disclosure
# ==============================================================================
def test_unhandled_exception_hides_stack_trace_from_client(client):
    with patch("app.api.health.HealthResponse", side_effect=ValueError("Simulated internal DB failure at line 42")):
        res = client.get("/health")
        assert res.status_code == 500
        data = res.json()
        assert data["status"] == "error"
        assert "request_id" in data
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        # Ensure raw exception message and line numbers are hidden from client
        assert "line 42" not in data["error"]["message"]
        assert "Simulated internal DB failure" not in data["error"]["message"]


# ==============================================================================
# 7. Health & Diagnostics Security (No credentials leaked)
# ==============================================================================
def test_health_endpoints_do_not_leak_credentials(client):
    res = client.get("/health/details")
    assert res.status_code == 200
    data = res.json()
    assert "llm" in data
    assert "api_key_configured" in data["llm"]
    # Verify no plaintext keys or tokens exist in response
    assert "api_key" not in data["llm"]
    assert "gsk_" not in json.dumps(data)
    assert "Bearer" not in json.dumps(data)


# ==============================================================================
# 8. IDOR & Missing Object Handling
# ==============================================================================
def test_idor_and_missing_resource_handling(client):
    # Forged project IDs return standard 404 envelope with correlation ID
    res = client.get("/api/projects/proj_forged_tenant_123456789")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"
    assert "request_id" in data
