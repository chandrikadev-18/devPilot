"""
DevPilot Change Execution Engine (v2.2).

Safely executes APPROVED change proposals by:
1. Verifying proposal existence and APPROVED status.
2. Running pre-flight validations and staleness detection.
3. Creating atomic backup checkpoints.
4. Applying unified diff patches.
5. Validating Python syntax and AST integrity on modified files.
6. Running targeted and repository test suites.
7. Automatically rolling back on validation or test failures.
8. Updating proposal status to APPLIED upon success.
"""

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from app.agent.tools import resolve_safe_path
from app.changes.approval import (
    AlreadyAppliedError,
    ProposalNotFoundError,
    RejectedProposalError,
)
from app.changes.models import (
    ChangeExecution,
    ChangeProposal,
    ExecutionStatus,
    ProposalStatus,
    TestValidationResult,
)
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.proposal_store import ProposalStore, compute_file_hash
from app.changes.rollback import RollbackManager
from app.changes.test_runner import TestRunner
from app.git.repository import is_git_repository


class ExecutionError(Exception):
    """Base exception for change proposal execution."""
    pass


class UnapprovedProposalError(ExecutionError):
    """Raised when attempting to execute a proposal that is not APPROVED."""
    pass


class InvalidPatchError(ExecutionError):
    """Raised when the patch is malformed, empty, or unapplicable."""
    pass


class StalePatchError(ExecutionError):
    """Raised when repository files have drifted since proposal creation."""
    pass


class PatchExecutionError(ExecutionError):
    """Raised when applying the patch fails."""
    pass


class SyntaxValidationError(ExecutionError):
    """Raised when modified files contain syntax or AST errors."""
    pass


class TestExecutionFailureError(ExecutionError):
    """Raised when post-apply tests fail."""
    __test__ = False



class ChangeExecutor:
    """
    Executes approved change proposals safely with pre-flight checks,
    atomic checkpoints, syntax validation, test validation, and automatic rollback.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        store: Optional[ProposalStore] = None,
        validator: Optional[PatchValidator] = None,
        applier: Optional[PatchApplier] = None,
        rollback_manager: Optional[RollbackManager] = None,
        test_runner: Optional[TestRunner] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.store = store or ProposalStore(project_root=self.project_root)
        self.validator = validator or PatchValidator(project_root=self.project_root)
        self.applier = applier or PatchApplier(project_root=self.project_root)
        self.rollback_manager = rollback_manager or RollbackManager(project_root=self.project_root)
        self.test_runner = test_runner or TestRunner(project_root=self.project_root)
        self.executions_dir = self.project_root / "data" / "executions"

    def _generate_execution_id(self) -> str:
        now_utc = datetime.now(timezone.utc)
        ts = now_utc.strftime("%Y%m%d_%H%M%S")
        rand_suffix = uuid.uuid4().hex[:6]
        return f"exec_{ts}_{rand_suffix}"

    def _save_execution(self, execution: ChangeExecution) -> None:
        try:
            self.executions_dir.mkdir(parents=True, exist_ok=True)
            if execution.execution_id:
                exec_file = self.executions_dir / f"{execution.execution_id}.json"
                with open(exec_file, "w", encoding="utf-8") as f:
                    json.dump(execution.to_dict(), f, indent=2)
            latest_file = self.executions_dir / "latest.json"
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(execution.to_dict(), f, indent=2)
        except Exception:
            pass

    def get_proposal(self, proposal_id: str) -> ChangeProposal:
        """
        Loads a proposal by ID. Raises ProposalNotFoundError if not found.
        """
        proposal = self.store.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal '{proposal_id}' was not found.")
        return proposal

    def execute(
        self,
        proposal_id: str,
        run_tests: bool = True,
        target_tests: Optional[List[str]] = None,
        raise_on_error: bool = False,
    ) -> ChangeExecution:
        """
        Executes an APPROVED change proposal safely.

        Workflow:
        1. Load & verify proposal is APPROVED.
        2. Validate patch & pre-flight repository consistency.
        3. Create atomic checkpoint.
        4. Apply patch.
        5. Validate Python syntax on changed files.
        6. Run validation tests.
        7. On failure: automatically rollback checkpoint and restore repository.
        8. On success: update proposal status to APPLIED and persist changes.
        """
        # 1. Load Proposal
        proposal = self.get_proposal(proposal_id)

        # 2. Strict Approval Verification (MUST NEVER EXECUTE UNAPPROVED PROPOSALS)
        if proposal.status == ProposalStatus.APPLIED.value:
            raise AlreadyAppliedError(f"Proposal '{proposal_id}' has already been APPLIED.")
        if proposal.status == ProposalStatus.REJECTED.value:
            raise RejectedProposalError(f"Cannot execute proposal '{proposal_id}' because it was REJECTED.")
        if proposal.status != ProposalStatus.APPROVED.value:
            raise UnapprovedProposalError(
                f"Cannot execute proposal '{proposal_id}' because it is in status '{proposal.status}'. "
                f"Only APPROVED proposals can be executed."
            )

        execution_id = self._generate_execution_id()
        started_at = datetime.now(timezone.utc).isoformat()
        steps = {
            "pre_flight": "PENDING",
            "patch_validation": "PENDING",
            "patch_application": "PENDING",
            "tests": "PENDING",
            "repo_state": "PENDING",
        }

        execution = ChangeExecution(
            proposal_id=proposal_id,
            execution_id=execution_id,
            status=ExecutionStatus.RUNNING.value,
            mode="APPROVED_EXECUTION",
            started_at=started_at,
            steps=steps,
        )

        checkpoint_id: Optional[str] = None

        try:
            # 3. Pre-Flight Checks & Target Drift Verification
            if not proposal.patch or not proposal.patch.strip():
                steps["pre_flight"] = "FAIL"
                steps["patch_validation"] = "FAIL"
                err_msg = f"Proposal '{proposal_id}' contains no valid patch."
                execution.error = err_msg
                execution.status = ExecutionStatus.FAILED.value
                execution.rollback_status = "NONE"
                execution.completed_at = datetime.now(timezone.utc).isoformat()
                self._save_execution(execution)
                if raise_on_error:
                    raise InvalidPatchError(err_msg)
                return execution

            if proposal.target_file:
                try:
                    target_path = resolve_safe_path(proposal.target_file, self.project_root)
                except Exception as e:
                    steps["pre_flight"] = "FAIL"
                    err_msg = f"Target file path '{proposal.target_file}' is invalid: {e}"
                    execution.error = err_msg
                    execution.status = ExecutionStatus.FAILED.value
                    execution.rollback_status = "NONE"
                    execution.completed_at = datetime.now(timezone.utc).isoformat()
                    self._save_execution(execution)
                    if raise_on_error:
                        raise StalePatchError(err_msg)
                    return execution

                if not target_path.exists() or not target_path.is_file():
                    steps["pre_flight"] = "FAIL"
                    err_msg = f"Target file '{proposal.target_file}' does not exist on disk."
                    execution.error = err_msg
                    execution.status = ExecutionStatus.FAILED.value
                    execution.rollback_status = "NONE"
                    execution.completed_at = datetime.now(timezone.utc).isoformat()
                    self._save_execution(execution)
                    if raise_on_error:
                        raise StalePatchError(err_msg)
                    return execution

                if proposal.target_content_hash:
                    curr_hash = compute_file_hash(target_path)
                    if curr_hash != proposal.target_content_hash:
                        steps["pre_flight"] = "FAIL"
                        err_msg = (
                            f"Target file '{proposal.target_file}' has been modified on disk since proposal creation. "
                            f"Execution rejected to prevent conflicting overwrites."
                        )
                        execution.error = err_msg
                        execution.status = ExecutionStatus.FAILED.value
                        execution.rollback_status = "NONE"
                        execution.completed_at = datetime.now(timezone.utc).isoformat()
                        self._save_execution(execution)
                        if raise_on_error:
                            raise StalePatchError(err_msg)
                        return execution

            steps["pre_flight"] = "PASS"

            # 4. Patch Structure Validation
            val_res = self.validator.validate(proposal.patch)
            execution.validation_result = val_res

            if not val_res.is_valid:
                steps["patch_validation"] = "FAIL"
                err_msg = "; ".join(val_res.errors) if val_res.errors else "Patch validation failed."
                execution.error = err_msg
                execution.status = ExecutionStatus.FAILED.value
                execution.rollback_status = "NONE"
                execution.completed_at = datetime.now(timezone.utc).isoformat()
                self._save_execution(execution)
                if raise_on_error:
                    raise InvalidPatchError(err_msg)
                return execution

            steps["patch_validation"] = "PASS"
            execution.status = ExecutionStatus.VALIDATED.value

            # 5. Create Pre-Modification Safety Checkpoint
            affected_files = val_res.files_affected
            if not affected_files and proposal.target_file:
                affected_files = [proposal.target_file]
            checkpoint_id = self.rollback_manager.create_checkpoint(affected_files)
            execution.checkpoint_id = checkpoint_id

            # 6. Apply Patch
            try:
                applied_files = self.applier.apply_patch(proposal.patch)
            except Exception as e:
                # Rollback on patch application failure
                self.rollback_manager.restore_checkpoint(checkpoint_id)
                steps["patch_application"] = "FAIL"
                steps["repo_state"] = "RESTORED"
                err_msg = f"Patch application failed: {str(e)}"
                execution.error = err_msg
                execution.status = ExecutionStatus.FAILED.value
                execution.rollback_status = "SUCCESS"
                execution.completed_at = datetime.now(timezone.utc).isoformat()
                self._save_execution(execution)
                if raise_on_error:
                    raise PatchExecutionError(err_msg)
                return execution

            execution.changed_files = applied_files
            steps["patch_application"] = "PASS"
            execution.status = ExecutionStatus.APPLIED.value

            # 7. Post-Apply Syntax & Integrity Validation
            for changed_rel in applied_files:
                if changed_rel.endswith(".py"):
                    try:
                        changed_path = resolve_safe_path(changed_rel, self.project_root)
                        if changed_path.exists() and changed_path.is_file():
                            with open(changed_path, "r", encoding="utf-8", errors="replace") as f:
                                code_text = f.read()
                            ast.parse(code_text, filename=str(changed_path))
                    except SyntaxError as e:
                        # Syntax error detected -> immediate rollback
                        self.rollback_manager.restore_checkpoint(checkpoint_id)
                        steps["patch_application"] = "FAIL"
                        steps["repo_state"] = "RESTORED"
                        err_msg = f"Syntax validation failed in '{changed_rel}': {e.msg} (line {e.lineno})"
                        execution.error = err_msg
                        execution.status = ExecutionStatus.FAILED.value
                        execution.rollback_status = "SUCCESS"
                        execution.completed_at = datetime.now(timezone.utc).isoformat()
                        self._save_execution(execution)
                        if raise_on_error:
                            raise SyntaxValidationError(err_msg)
                        return execution

            # 8. Post-Apply Test Validation
            execution.status = ExecutionStatus.TESTING.value
            if run_tests:
                tests_to_run = target_tests or (list(proposal.tests_to_update) + list(proposal.tests_to_add))
                test_res = self.test_runner.run_tests(test_targets=tests_to_run if tests_to_run else None)
                execution.test_result = test_res

                if not test_res.is_success:
                    # Tests failed -> automatic rollback
                    self.rollback_manager.restore_checkpoint(checkpoint_id)
                    steps["tests"] = "FAIL"
                    steps["repo_state"] = "RESTORED"
                    err_msg = f"Validation tests failed ({test_res.failed} test(s) failed). Changes were automatically rolled back."
                    execution.error = err_msg
                    execution.status = ExecutionStatus.FAILED.value
                    execution.rollback_status = "SUCCESS"
                    execution.completed_at = datetime.now(timezone.utc).isoformat()
                    self._save_execution(execution)
                    if raise_on_error:
                        raise TestExecutionFailureError(err_msg)
                    return execution

                steps["tests"] = "PASS"
            else:
                steps["tests"] = "SKIPPED"

            # 9. Extract Git Diff if Available
            if is_git_repository(self.project_root):
                try:
                    import git
                    repo = git.Repo(self.project_root)
                    diff_text = repo.git.diff()
                    execution.diff = diff_text
                except Exception:
                    pass

            # 10. Finalize Successful Execution
            steps["repo_state"] = "CLEAN"
            execution.status = ExecutionStatus.SUCCESS.value
            execution.rollback_status = "NOT_NEEDED"
            execution.completed_at = datetime.now(timezone.utc).isoformat()

            # Update Proposal State
            proposal.status = ProposalStatus.APPLIED.value
            proposal.applied_at = execution.completed_at
            self.store.save(proposal)

            self._save_execution(execution)
            return execution

        except (UnapprovedProposalError, ProposalNotFoundError, AlreadyAppliedError, RejectedProposalError):
            raise
        except Exception as e:
            if checkpoint_id:
                try:
                    self.rollback_manager.restore_checkpoint(checkpoint_id)
                    execution.rollback_status = "SUCCESS"
                    steps["repo_state"] = "RESTORED"
                except Exception:
                    execution.rollback_status = "FAILED"
            execution.error = str(e)
            execution.status = ExecutionStatus.FAILED.value
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_execution(execution)
            if raise_on_error:
                raise ExecutionError(str(e))
            return execution
