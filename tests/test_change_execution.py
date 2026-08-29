"""
Tests for DevPilot v2.2 — Approved Change Execution Engine.

Covers:
1. Approved proposal executes successfully and updates status to APPLIED
2. Pending proposal cannot execute (UnapprovedProposalError)
3. Rejected proposal cannot execute (RejectedProposalError)
4. Nonexistent proposal cannot execute (ProposalNotFoundError / 404)
5. Invalid patch detection and rejection (InvalidPatchError)
6. Stale patch / drift detection when target file changes on disk
7. Patch application failure triggers clean rollback
8. Syntax validation failure triggers automatic rollback
9. Test failure triggers automatic rollback and repository restoration
10. Successful execution preserves changes in working tree
11. Rollback restores exact original file contents
12. CLI execution text output formatting
13. CLI execution JSON output formatting
14. FastAPI REST API POST /changes/{proposal_id}/execute
15. Execution status transitions and step reporting
16. Unrelated working tree changes are preserved during execution and rollback
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.changes.approval import (
    AlreadyAppliedError,
    ApprovalService,
    ProposalNotFoundError,
    RejectedProposalError,
)
from app.changes.executor import (
    ChangeExecutor,
    ExecutionError,
    InvalidPatchError,
    StalePatchError,
    SyntaxValidationError,
    TestExecutionFailureError,
    UnapprovedProposalError,
)
from app.changes.models import (
    ChangeExecution,
    ChangeProposal,
    ExecutionStatus,
    ProposalStatus,
)
from app.changes.proposal_generator import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore, compute_file_hash
from app.main import app, run_execute


@pytest.fixture
def temp_codebase(tmp_path: Path):
    """Creates a temporary isolated codebase for change execution tests."""
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    builder_file = app_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self, files):\n"
        "        graph = {}\n"
        "        for f in files:\n"
        "            graph[f] = []\n"
        "        return graph\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_builder.py"
    test_file.write_text(
        "from app.builder import GraphBuilder\n"
        "\n"
        "def test_build():\n"
        "    gb = GraphBuilder()\n"
        "    assert gb.build(['a.py']) == {'a.py': []}\n",
        encoding="utf-8",
    )

    # Add an unrelated file to test preservation
    unrelated_file = app_dir / "unrelated.py"
    unrelated_file.write_text(
        "# Important unrelated code\n"
        "def calculate_total(items):\n"
        "    return sum(items)\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


def _create_and_approve_proposal(codebase: Path, request_str: str = "Add logging when GraphBuilder.build starts and finishes") -> ChangeProposal:
    generator = ChangeProposalGenerator(project_root=codebase)
    proposal = generator.propose(request_str)
    approval_svc = ApprovalService(project_root=codebase)
    approved = approval_svc.approve_proposal(proposal.proposal_id, reason="Approved for execution", force=True)
    return approved


# ==============================================================================
# 1. Successful Execution of Approved Proposal
# ==============================================================================

def test_approved_proposal_executes_successfully(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)
    assert approved.status == ProposalStatus.APPROVED.value

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=True)

    assert execution.status == ExecutionStatus.SUCCESS.value
    assert execution.proposal_id == approved.proposal_id
    assert execution.execution_id is not None
    assert execution.steps["pre_flight"] == "PASS"
    assert execution.steps["patch_validation"] == "PASS"
    assert execution.steps["patch_application"] == "PASS"
    assert execution.steps["tests"] == "PASS"
    assert execution.steps["repo_state"] == "CLEAN"
    assert len(execution.changed_files) > 0

    # Verify changes were applied to file on disk
    target_file = temp_codebase / "app" / "builder.py"
    content = target_file.read_text(encoding="utf-8")
    assert "build starts" in content or "logger" in content or "logging" in content

    # Verify proposal status in store was updated to APPLIED
    store = ProposalStore(project_root=temp_codebase)
    updated_prop = store.get(approved.proposal_id)
    assert updated_prop.status == ProposalStatus.APPLIED.value
    assert updated_prop.applied_at is not None


# ==============================================================================
# 2. Strict Approval Gating: Pending & Rejected Proposals Cannot Execute
# ==============================================================================

def test_pending_proposal_cannot_execute(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")
    assert proposal.status in (ProposalStatus.PENDING_APPROVAL.value, ProposalStatus.PROPOSAL_ONLY.value)

    executor = ChangeExecutor(project_root=temp_codebase)
    with pytest.raises(UnapprovedProposalError) as exc_info:
        executor.execute(proposal.proposal_id)

    assert "Only APPROVED proposals can be executed" in str(exc_info.value)

    # Verify file was NOT modified
    builder_file = temp_codebase / "app" / "builder.py"
    assert "logger" not in builder_file.read_text(encoding="utf-8")


def test_rejected_proposal_cannot_execute(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")
    
    approval_svc = ApprovalService(project_root=temp_codebase)
    approval_svc.reject_proposal(proposal.proposal_id, reason="Not needed right now")

    executor = ChangeExecutor(project_root=temp_codebase)
    with pytest.raises(RejectedProposalError):
        executor.execute(proposal.proposal_id)


def test_already_applied_proposal_cannot_execute_twice(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)
    executor = ChangeExecutor(project_root=temp_codebase)
    
    # First execution succeeds
    res1 = executor.execute(approved.proposal_id, run_tests=True)
    assert res1.status == ExecutionStatus.SUCCESS.value

    # Second execution is blocked
    with pytest.raises(AlreadyAppliedError):
        executor.execute(approved.proposal_id)


# ==============================================================================
# 3. Missing Proposal Handling
# ==============================================================================

def test_missing_proposal_cannot_execute(temp_codebase: Path):
    executor = ChangeExecutor(project_root=temp_codebase)
    with pytest.raises(ProposalNotFoundError):
        executor.execute("prop_nonexistent_999999")


# ==============================================================================
# 4. Invalid Patch Rejection
# ==============================================================================

def test_invalid_patch_execution_failure(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)
    # Corrupt patch in store
    store = ProposalStore(project_root=temp_codebase)
    approved.patch = "This is not a valid diff header\n+bad code"
    store.save(approved)

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=False)

    assert execution.status == ExecutionStatus.FAILED.value
    assert execution.steps["patch_validation"] == "FAIL"


def test_empty_patch_execution_failure(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)
    store = ProposalStore(project_root=temp_codebase)
    approved.patch = ""
    store.save(approved)

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=False)

    assert execution.status == ExecutionStatus.FAILED.value
    assert execution.steps["pre_flight"] == "FAIL"


# ==============================================================================
# 5. Stale Patch / Drift Detection
# ==============================================================================

def test_stale_patch_detection_when_target_file_modified(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)

    # Modify the target file externally to simulate drift
    target_file = temp_codebase / "app" / "builder.py"
    target_file.write_text(
        "# Externally modified\n"
        "class GraphBuilder:\n"
        "    def build(self, files):\n"
        "        return {f: [] for f in files}\n",
        encoding="utf-8",
    )

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=False)

    assert execution.status == ExecutionStatus.FAILED.value
    assert execution.steps["pre_flight"] == "FAIL"
    assert "modified on disk since proposal creation" in execution.error


# ==============================================================================
# 6. Syntax Validation Failure Triggers Rollback
# ==============================================================================

def test_syntax_validation_failure_triggers_rollback(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)

    original_code = (temp_codebase / "app" / "builder.py").read_text(encoding="utf-8")

    # Construct a patch that applies successfully as unified diff but causes a Python syntax error
    syntax_error_patch = (
        "--- a/app/builder.py\n"
        "+++ b/app/builder.py\n"
        "@@ -1,6 +1,6 @@\n"
        " class GraphBuilder:\n"
        "-    def build(self, files):\n"
        "+    def build(self, files)\n"  # Missing colon -> SyntaxError
        "         graph = {}\n"
        "         for f in files:\n"
        "             graph[f] = []\n"
        "         return graph\n"
    )

    store = ProposalStore(project_root=temp_codebase)
    approved.patch = syntax_error_patch
    store.save(approved)

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=False)

    assert execution.status == ExecutionStatus.FAILED.value
    assert execution.rollback_status == "SUCCESS"
    assert "Syntax validation failed" in execution.error
    assert execution.steps["repo_state"] == "RESTORED"

    # Verify repository was cleanly restored
    restored_code = (temp_codebase / "app" / "builder.py").read_text(encoding="utf-8")
    assert restored_code == original_code


# ==============================================================================
# 7. Test Failure Triggers Rollback & Restores Repository
# ==============================================================================

def test_test_failure_triggers_automatic_rollback(temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)
    original_code = (temp_codebase / "app" / "builder.py").read_text(encoding="utf-8")

    # Construct a patch that breaks the test (returns empty dict instead of {'a.py': []})
    breaking_patch = (
        "--- a/app/builder.py\n"
        "+++ b/app/builder.py\n"
        "@@ -1,6 +1,6 @@\n"
        " class GraphBuilder:\n"
        "     def build(self, files):\n"
        "-        graph = {}\n"
        "-        for f in files:\n"
        "-            graph[f] = []\n"
        "-        return graph\n"
        "+        return {}\n"
    )

    store = ProposalStore(project_root=temp_codebase)
    approved.patch = breaking_patch
    store.save(approved)

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=True)

    assert execution.status == ExecutionStatus.FAILED.value
    assert execution.rollback_status == "SUCCESS"
    assert execution.steps["tests"] == "FAIL"
    assert execution.steps["repo_state"] == "RESTORED"
    assert "Validation tests failed" in execution.error

    # Verify repository files returned to previous pristine state
    restored_code = (temp_codebase / "app" / "builder.py").read_text(encoding="utf-8")
    assert restored_code == original_code


# ==============================================================================
# 8. Unrelated Working Tree Changes Preserved
# ==============================================================================

def test_unrelated_files_preserved_on_execution_and_rollback(temp_codebase: Path):
    unrelated_file = temp_codebase / "app" / "unrelated.py"
    unrelated_content = unrelated_file.read_text(encoding="utf-8")

    approved = _create_and_approve_proposal(temp_codebase)

    executor = ChangeExecutor(project_root=temp_codebase)
    execution = executor.execute(approved.proposal_id, run_tests=True)
    assert execution.status == ExecutionStatus.SUCCESS.value

    # Verify unrelated file was completely untouched
    assert unrelated_file.read_text(encoding="utf-8") == unrelated_content


# ==============================================================================
# 9. CLI Execution: Text & JSON
# ==============================================================================

def test_cli_execution_human_readable(temp_codebase: Path, capsys):
    approved = _create_and_approve_proposal(temp_codebase)

    run_execute(
        proposal_id=approved.proposal_id,
        project_dir=str(temp_codebase),
        no_tests=False,
        as_json=False,
    )

    captured = capsys.readouterr()
    assert "DevPilot v2.2 — Change Execution" in captured.out
    assert f"Proposal: {approved.proposal_id}" in captured.out
    assert "Status: APPROVED" in captured.out
    assert "Pre-flight: PASS" in captured.out
    assert "Patch validation: PASS" in captured.out
    assert "Patch application: PASS" in captured.out
    assert "Tests: PASS" in captured.out
    assert "Repository state: CLEAN" in captured.out
    assert "Execution Result: SUCCESS" in captured.out


def test_cli_execution_json(temp_codebase: Path, capsys):
    approved = _create_and_approve_proposal(temp_codebase)

    run_execute(
        proposal_id=approved.proposal_id,
        project_dir=str(temp_codebase),
        no_tests=False,
        as_json=True,
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["proposal_id"] == approved.proposal_id
    assert data["status"] == "SUCCESS"
    assert data["steps"]["pre_flight"] == "PASS"
    assert data["steps"]["tests"] == "PASS"


def test_cli_execution_unapproved_proposal_fails(temp_codebase: Path, capsys):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    with pytest.raises(SystemExit):
        run_execute(
            proposal_id=proposal.proposal_id,
            project_dir=str(temp_codebase),
            as_json=False,
        )

    captured = capsys.readouterr()
    assert "Error executing proposal" in captured.err or "Error" in captured.err


# ==============================================================================
# 10. FastAPI REST API Endpoint
# ==============================================================================

def test_api_execute_approved_proposal(client: TestClient, temp_codebase: Path):
    approved = _create_and_approve_proposal(temp_codebase)

    response = client.post(
        f"/changes/{approved.proposal_id}/execute",
        json={"project_dir": str(temp_codebase), "run_tests": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["proposal_id"] == approved.proposal_id
    assert data["status"] == "SUCCESS"
    assert data["steps"]["tests"] == "PASS"
    assert len(data["changed_files"]) > 0


def test_api_execute_unapproved_proposal_rejected(client: TestClient, temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    response = client.post(
        f"/changes/{proposal.proposal_id}/execute",
        json={"project_dir": str(temp_codebase), "run_tests": True},
    )

    assert response.status_code == 400
    assert "Only APPROVED proposals can be executed" in response.json()["detail"]


def test_api_execute_missing_proposal_returns_404(client: TestClient, temp_codebase: Path):
    response = client.post(
        "/changes/prop_nonexistent_12345/execute",
        json={"project_dir": str(temp_codebase)},
    )
    assert response.status_code == 404
