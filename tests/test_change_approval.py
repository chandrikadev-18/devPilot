"""
Tests for DevPilot v2.2 — Change Approval & Human-in-the-Loop Workflow.

Covers:
1. Proposal creation with persistent metadata & assigned proposal_id
2. Initial status PENDING_APPROVAL
3. Human approval workflow and metadata recording
4. Rejection workflow and metadata recording
5. Nonexistent proposal ID handling (ProposalNotFoundError / 404)
6. Protection against duplicate approval (DuplicateApprovalError)
7. Protection against approving an already-rejected proposal (RejectedProposalError)
8. Protection against approving an already-applied proposal (AlreadyAppliedError)
9. Stronger confirmation requirement for HIGH-risk proposals (HighRiskConfirmationError unless force=True)
10. Stale proposal detection when target file changes on disk after proposal creation (StaleProposalError)
11. Proposal inspection by ID via ProposalStore and CLI
12. CLI commands: `proposal <id>`, `approve <id>`, `reject <id>` (text & JSON)
13. FastAPI approval REST API endpoints
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

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
from app.changes.proposal import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore
from app.main import app, run_approve, run_proposal, run_propose, run_reject


@pytest.fixture
def temp_codebase(tmp_path: Path):
    """Creates a temporary isolated codebase for proposal approval tests."""
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

    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Proposal Store & Metadata Persistence
# ==============================================================================

def test_proposal_creation_and_pending_status(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    assert proposal.proposal_id is not None
    assert proposal.proposal_id.startswith("prop_")
    assert proposal.status in (ProposalStatus.PENDING_APPROVAL.value, ProposalStatus.PROPOSAL_ONLY.value)
    assert proposal.target_content_hash is not None

    # Retrieve from store
    store = ProposalStore(project_root=temp_codebase)
    saved = store.get(proposal.proposal_id)
    assert saved is not None
    assert saved.proposal_id == proposal.proposal_id
    assert saved.status in (ProposalStatus.PENDING_APPROVAL.value, ProposalStatus.PROPOSAL_ONLY.value)
    assert saved.target_symbol == "GraphBuilder.build"


# ==============================================================================
# 2. Approval Workflow & Safety Checks
# ==============================================================================

def test_approve_proposal_success(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    service = ApprovalService(project_root=temp_codebase)
    approved = service.approve_proposal(
        proposal_id=proposal.proposal_id,
        reason="Looks good to go",
        force=True,
    )

    assert approved.status == ProposalStatus.APPROVED.value
    assert approved.decision == "approved"
    assert approved.decision_reason == "Looks good to go"
    assert approved.approved_at is not None

    # Verify saved state in store
    store = ProposalStore(project_root=temp_codebase)
    reloaded = store.get(proposal.proposal_id)
    assert reloaded.status == ProposalStatus.APPROVED.value


def test_high_risk_requires_confirmation(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    # Mark proposal as HIGH risk
    proposal.risk = "HIGH"
    store = ProposalStore(project_root=temp_codebase)
    store.save(proposal)

    service = ApprovalService(project_root=temp_codebase)
    # Without force=True, approving HIGH risk must raise HighRiskConfirmationError
    with pytest.raises(HighRiskConfirmationError):
        service.approve_proposal(proposal_id=proposal.proposal_id, force=False)

    # With force=True, approving HIGH risk succeeds
    approved = service.approve_proposal(proposal_id=proposal.proposal_id, force=True)
    assert approved.status == ProposalStatus.APPROVED.value


def test_approve_nonexistent_proposal(temp_codebase: Path):
    service = ApprovalService(project_root=temp_codebase)
    with pytest.raises(ProposalNotFoundError):
        service.approve_proposal("prop_nonexistent_9999", force=True)


def test_duplicate_approval_prevention(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    service = ApprovalService(project_root=temp_codebase)
    service.approve_proposal(proposal.proposal_id, force=True)

    # Second approval attempt must raise DuplicateApprovalError
    with pytest.raises(DuplicateApprovalError):
        service.approve_proposal(proposal.proposal_id, force=True)


def test_reject_proposal_workflow(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    service = ApprovalService(project_root=temp_codebase)
    rejected = service.reject_proposal(proposal.proposal_id, reason="Not needed at this time")

    assert rejected.status == ProposalStatus.REJECTED.value
    assert rejected.decision == "rejected"
    assert rejected.decision_reason == "Not needed at this time"
    assert rejected.rejected_at is not None


def test_cannot_approve_rejected_proposal(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    service = ApprovalService(project_root=temp_codebase)
    service.reject_proposal(proposal.proposal_id)

    with pytest.raises(RejectedProposalError):
        service.approve_proposal(proposal.proposal_id, force=True)


def test_cannot_approve_or_reject_applied_proposal(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    # Manually mark as applied
    store = ProposalStore(project_root=temp_codebase)
    proposal.status = ProposalStatus.APPLIED.value
    store.save(proposal)

    service = ApprovalService(project_root=temp_codebase, store=store)
    with pytest.raises(AlreadyAppliedError):
        service.approve_proposal(proposal.proposal_id, force=True)

    with pytest.raises(AlreadyAppliedError):
        service.reject_proposal(proposal.proposal_id)


def test_stale_proposal_detection_on_file_change(temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    # Modify target file on disk after proposal creation
    builder_file = temp_codebase / "app" / "builder.py"
    builder_file.write_text("def completely_different_code(): pass\n", encoding="utf-8")

    service = ApprovalService(project_root=temp_codebase)
    with pytest.raises(StaleProposalError):
        service.approve_proposal(proposal.proposal_id, force=True)


# ==============================================================================
# 3. CLI Command Tests (proposal, approve, reject)
# ==============================================================================

def test_cli_proposal_inspect(temp_codebase: Path, capsys):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    run_proposal(proposal_id=proposal.proposal_id, project_dir=str(temp_codebase), as_json=False)
    captured = capsys.readouterr()

    assert proposal.proposal_id in captured.out
    assert "GraphBuilder.build" in captured.out
    assert "PENDING_APPROVAL" in captured.out or "PROPOSAL_ONLY" in captured.out


def test_cli_proposal_inspect_json(temp_codebase: Path, capsys):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    run_proposal(proposal_id=proposal.proposal_id, project_dir=str(temp_codebase), as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["proposal_id"] == proposal.proposal_id
    assert data["status"] in ("PENDING_APPROVAL", "PROPOSAL_ONLY")
    assert data["target_symbol"] == "GraphBuilder.build"


def test_cli_approve_command(temp_codebase: Path, capsys):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    run_approve(
        proposal_id=proposal.proposal_id,
        reason="Approved for testing",
        force=True,
        project_dir=str(temp_codebase),
        as_json=False,
    )
    captured = capsys.readouterr()

    assert "DevPilot v2.2 — Proposal Approved" in captured.out
    assert proposal.proposal_id in captured.out
    assert "APPROVED" in captured.out


def test_cli_reject_command(temp_codebase: Path, capsys):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    run_reject(
        proposal_id=proposal.proposal_id,
        reason="Rejected for testing",
        project_dir=str(temp_codebase),
        as_json=False,
    )
    captured = capsys.readouterr()

    assert "DevPilot v2.2 — Proposal Rejected" in captured.out
    assert proposal.proposal_id in captured.out
    assert "REJECTED" in captured.out


# ==============================================================================
# 4. REST API Endpoint Tests
# ==============================================================================

def test_api_proposal_inspect_and_approve(client: TestClient, temp_codebase: Path):
    generator = ChangeProposalGenerator(project_root=temp_codebase)
    proposal = generator.propose("Add logging when GraphBuilder.build starts and finishes")

    # 1. Get proposal by ID
    get_res = client.get(f"/api/changes/proposals/{proposal.proposal_id}?project_dir={temp_codebase}")
    assert get_res.status_code == 200
    assert get_res.json()["proposal_id"] == proposal.proposal_id

    # 2. Approve proposal
    app_res = client.post(
        f"/api/changes/proposals/{proposal.proposal_id}/approve",
        json={"reason": "Approved via API", "force": True, "project_dir": str(temp_codebase)},
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"
    assert app_res.json()["decision"] == "approved"
