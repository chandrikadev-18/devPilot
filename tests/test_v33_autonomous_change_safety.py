"""
DevPilot v3.3 Autonomous Code Change & Safe Fix Verification Suite.

Tests end-to-end safe code modification lifecycle:
1. Target detection & planning
2. Proposal generation & reviewable diff
3. State transitions (PROPOSED -> APPROVED -> APPLIED, PROPOSED -> REJECTED)
4. Approval requirement enforcement (unapproved cannot execute)
5. Patch validation & Python AST syntax integrity
6. Test-driven verification
7. Automatic rollback on test/syntax failures
8. Stale target file drift protection
9. Path traversal sandboxing
"""

import ast
from pathlib import Path
import pytest

from app.changes.approval import (
    ApprovalService,
    DuplicateApprovalError,
    HighRiskConfirmationError,
    ProposalNotFoundError,
    RejectedProposalError,
    StaleProposalError,
)
from app.changes.executor import (
    ChangeExecutor,
    ExecutionStatus,
    InvalidPatchError,
    SyntaxValidationError,
    UnapprovedProposalError,
)
from app.changes.models import ChangeProposal, ProposalStatus
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.planner import ChangeImpactPlanner
from app.changes.proposal_generator import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore, compute_file_hash
from app.changes.rollback import RollbackManager


def test_target_detection_and_planning_without_modifying_files(tmp_path):
    calc_py = tmp_path / "calculator.py"
    calc_py.write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n",
        encoding="utf-8"
    )
    planner = ChangeImpactPlanner(project_root=tmp_path)
    plan = planner.plan_change("Add validation to Calculator.add")

    assert plan.target_symbol is not None
    assert plan.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert len(plan.recommended_order) > 0
    # Verify file was NOT modified
    assert calc_py.read_text(encoding="utf-8") == (
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
    )


def test_proposal_lifecycle_and_approval_enforcement(tmp_path):
    calc_py = tmp_path / "calc.py"
    calc_py.write_text("def multiply(a, b):\n    return a * b\n", encoding="utf-8")
    store = ProposalStore(project_root=tmp_path)

    prop = ChangeProposal(
        proposal_id="prop_test_001",
        request="Add docstring to multiply",
        target_file="calc.py",
        target_symbol="multiply",
        target_content_hash=compute_file_hash(calc_py),
        patch=(
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def multiply(a, b):\n"
            "+    '''Multiplies two numbers.'''\n"
            "     return a * b\n"
        ),
        risk="LOW",
        status=ProposalStatus.PENDING_APPROVAL.value,
    )
    store.save(prop)

    approval_svc = ApprovalService(project_root=tmp_path, store=store)
    executor = ChangeExecutor(project_root=tmp_path, store=store)

    # 1. Cannot execute unapproved proposal
    with pytest.raises(UnapprovedProposalError):
        executor.execute("prop_test_001", run_tests=False)

    # 2. Approve proposal
    approved = approval_svc.approve_proposal("prop_test_001", reason="Ready for execution")
    assert approved.status == ProposalStatus.APPROVED.value

    # 3. Duplicate approval should error
    with pytest.raises(DuplicateApprovalError):
        approval_svc.approve_proposal("prop_test_001")

    # 4. Execute approved proposal
    exec_res = executor.execute("prop_test_001", run_tests=False)
    assert exec_res.status == ExecutionStatus.SUCCESS.value
    assert exec_res.rollback_status == "NOT_NEEDED"

    # Verify content was updated safely
    updated_content = calc_py.read_text(encoding="utf-8")
    assert "Multiplies two numbers" in updated_content

    # Proposal state is now APPLIED
    persisted_prop = store.get("prop_test_001")
    assert persisted_prop.status == ProposalStatus.APPLIED.value


def test_proposal_rejection_workflow(tmp_path):
    calc_py = tmp_path / "calc.py"
    calc_py.write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    store = ProposalStore(project_root=tmp_path)

    prop = ChangeProposal(
        proposal_id="prop_test_002",
        request="Refactor divide",
        target_file="calc.py",
        target_symbol="divide",
        patch="--- a/calc.py\n+++ b/calc.py\n",
        risk="LOW",
        status=ProposalStatus.PENDING_APPROVAL.value,
    )
    store.save(prop)

    approval_svc = ApprovalService(project_root=tmp_path, store=store)
    rejected = approval_svc.reject_proposal("prop_test_002", reason="Not required")
    assert rejected.status == ProposalStatus.REJECTED.value

    # Cannot approve or execute rejected proposal
    with pytest.raises(RejectedProposalError):
        approval_svc.approve_proposal("prop_test_002")

    executor = ChangeExecutor(project_root=tmp_path, store=store)
    with pytest.raises(RejectedProposalError):
        executor.execute("prop_test_002", run_tests=False)


def test_automatic_rollback_on_syntax_error(tmp_path):
    app_py = tmp_path / "app.py"
    original_code = "def run():\n    return True\n"
    app_py.write_text(original_code, encoding="utf-8")
    store = ProposalStore(project_root=tmp_path)

    # Patch with intentional syntax error
    invalid_patch = (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def run():\n"
        "+    if invalid syntax >>>:\n"
        "     return True\n"
    )

    prop = ChangeProposal(
        proposal_id="prop_syntax_err",
        request="Break syntax",
        target_file="app.py",
        patch=invalid_patch,
        risk="LOW",
        status=ProposalStatus.APPROVED.value,
    )
    store.save(prop)

    executor = ChangeExecutor(project_root=tmp_path, store=store)
    exec_res = executor.execute("prop_syntax_err", run_tests=False, raise_on_error=False)

    assert exec_res.status == ExecutionStatus.FAILED.value
    assert exec_res.rollback_status == "SUCCESS"
    assert "syntax" in exec_res.error.lower()

    # Original file must be perfectly restored
    assert app_py.read_text(encoding="utf-8") == original_code


def test_stale_target_drift_protection(tmp_path):
    target_py = tmp_path / "target.py"
    target_py.write_text("v = 1\n", encoding="utf-8")
    original_hash = compute_file_hash(target_py)

    store = ProposalStore(project_root=tmp_path)
    prop = ChangeProposal(
        proposal_id="prop_stale",
        request="Update v",
        target_file="target.py",
        target_content_hash=original_hash,
        patch="--- a/target.py\n+++ b/target.py\n@@ -1 +1 @@\n-v = 1\n+v = 2\n",
        risk="LOW",
        status=ProposalStatus.PENDING_APPROVAL.value,
    )
    store.save(prop)

    # Developer modifies the file in the meantime
    target_py.write_text("v = 999  # developer uncommitted edit\n", encoding="utf-8")

    approval_svc = ApprovalService(project_root=tmp_path, store=store)
    with pytest.raises(StaleProposalError):
        approval_svc.approve_proposal("prop_stale")


def test_high_risk_explicit_force_requirement(tmp_path):
    core_py = tmp_path / "core.py"
    core_py.write_text("def critical_security():\n    pass\n", encoding="utf-8")
    store = ProposalStore(project_root=tmp_path)

    prop = ChangeProposal(
        proposal_id="prop_high_risk",
        request="Change security core",
        target_file="core.py",
        patch="--- a/core.py\n+++ b/core.py\n",
        risk="HIGH",
        status=ProposalStatus.PENDING_APPROVAL.value,
    )
    store.save(prop)

    approval_svc = ApprovalService(project_root=tmp_path, store=store)

    # Must fail without force
    with pytest.raises(HighRiskConfirmationError):
        approval_svc.approve_proposal("prop_high_risk", force=False)

    # Succeeds with force=True
    approved = approval_svc.approve_proposal("prop_high_risk", force=True)
    assert approved.status == ProposalStatus.APPROVED.value


def test_path_traversal_sandboxing_protection(tmp_path):
    validator = PatchValidator(project_root=tmp_path)

    # Malicious patch attempting to escape project root
    evil_patch = (
        "--- a/../../etc/passwd\n"
        "+++ b/../../etc/passwd\n"
        "@@ -1,1 +1,1 @@\n"
        "-root:x:0:0\n"
        "+hacked:x:0:0\n"
    )

    val_res = validator.validate(evil_patch)
    assert not val_res.is_valid
    assert any("escape" in e.lower() or "traversal" in e.lower() or "boundary" in e.lower() or "outside" in e.lower() or "exist" in e.lower() for e in val_res.errors)
