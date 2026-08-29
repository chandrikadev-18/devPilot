"""
DevPilot v1.9 — Autonomous Code Fix Loop Orchestrator.

Coordinates the autonomous fix cycle:
User Request -> Analyze -> Plan -> Patch -> Validate -> Apply -> Test -> Review -> Success / Rollback.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.changes.models import (
    AutonomousFixResult,
    CodeChangePlan,
    CodeChangeProposal,
    FixMode,
    PatchValidationResult,
    RollbackResult,
    TestValidationResult,
)
from app.changes.patch import CodeChangePatchGenerator
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.planner import ChangeImpactPlanner
from app.changes.reviewer import GitChangeReviewer
from app.changes.rollback import RollbackManager
from app.changes.service import SafePatchService
from app.changes.test_runner import TestRunner
from app.git.repository import GitRepository, NotAGitRepositoryError
from app.graph.store import GraphStore


class AutonomousFixService:
    """
    Coordinates end-to-end autonomous code fixing with safe modes (PLAN, PATCH, AUTO),
    dirty working tree protections, test validation, intelligent review, and atomic rollbacks.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        planner: Optional[ChangeImpactPlanner] = None,
        patch_generator: Optional[CodeChangePatchGenerator] = None,
        validator: Optional[PatchValidator] = None,
        applier: Optional[PatchApplier] = None,
        rollback_manager: Optional[RollbackManager] = None,
        test_runner: Optional[TestRunner] = None,
        reviewer: Optional[GitChangeReviewer] = None,
        patch_service: Optional[SafePatchService] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.planner = planner or ChangeImpactPlanner(project_root=self.project_root)
        self.patch_generator = patch_generator or CodeChangePatchGenerator(project_root=self.project_root)
        self.validator = validator or PatchValidator(project_root=self.project_root)
        self.applier = applier or PatchApplier(project_root=self.project_root)
        self.rollback_manager = rollback_manager or RollbackManager(project_root=self.project_root)
        self.test_runner = test_runner or TestRunner(project_root=self.project_root)
        self.reviewer = reviewer or GitChangeReviewer(project_root=self.project_root)
        self.patch_service = patch_service or SafePatchService(
            project_root=self.project_root,
            validator=self.validator,
            applier=self.applier,
            rollback_manager=self.rollback_manager,
            test_runner=self.test_runner,
        )

    def execute(
        self,
        request: str,
        mode: FixMode = FixMode.PLAN,
        force: bool = False,
        graph: Optional[GraphStore] = None,
        llm: Optional[Any] = None,
    ) -> AutonomousFixResult:
        """
        Executes the autonomous fix workflow based on the requested mode.
        """
        if not request or not request.strip():
            return AutonomousFixResult(
                mode=mode,
                status="failed",
                request=request or "",
                phase="analyze",
                errors=["Change request cannot be empty."],
                message="Change request cannot be empty.",
            )

        clean_request = request.strip()

        # Parse mode if string passed
        if isinstance(mode, str):
            try:
                mode = FixMode(mode.upper())
            except ValueError:
                mode = FixMode.PLAN

        # ======================================================================
        # Mode: PLAN (Analyze & Plan without modifying repository)
        # ======================================================================
        if mode == FixMode.PLAN:
            return self._execute_plan_mode(clean_request, graph=graph)

        # ======================================================================
        # Mode: PATCH (Plan + Patch Generation + Validation without applying)
        # ======================================================================
        if mode == FixMode.PATCH:
            return self._execute_patch_mode(clean_request, graph=graph, llm=llm)

        # ======================================================================
        # Mode: AUTO (Plan -> Patch -> Validate -> Apply -> Test -> Review/Rollback)
        # ======================================================================
        if mode == FixMode.AUTO:
            return self._execute_auto_mode(clean_request, force=force, graph=graph, llm=llm)

        return AutonomousFixResult(
            mode=mode,
            status="failed",
            request=clean_request,
            phase="analyze",
            errors=[f"Unsupported fix mode: {mode}"],
            message=f"Unsupported fix mode: {mode}",
        )

    def _execute_plan_mode(
        self,
        request: str,
        graph: Optional[GraphStore] = None,
    ) -> AutonomousFixResult:
        """Executes PLAN mode."""
        try:
            plan = self.planner.plan_change(change_request=request, graph=graph)
            return AutonomousFixResult(
                mode=FixMode.PLAN,
                status="plan_only",
                request=request,
                phase="plan",
                plan=plan,
                message="Structured change plan constructed successfully based on repository evidence.",
            )
        except Exception as e:
            return AutonomousFixResult(
                mode=FixMode.PLAN,
                status="failed",
                request=request,
                phase="plan",
                errors=[str(e)],
                message=f"Failed to generate change plan: {str(e)}",
            )

    def _execute_patch_mode(
        self,
        request: str,
        graph: Optional[GraphStore] = None,
        llm: Optional[Any] = None,
    ) -> AutonomousFixResult:
        """Executes PATCH mode."""
        # 1. Plan
        try:
            plan = self.planner.plan_change(change_request=request, graph=graph)
        except Exception as e:
            return AutonomousFixResult(
                mode=FixMode.PATCH,
                status="failed",
                request=request,
                phase="plan",
                errors=[f"Planning failed: {str(e)}"],
                message=f"Planning failed: {str(e)}",
            )

        # 2. Generate Patch
        try:
            proposal = self.patch_generator.generate_patch(
                change_request=request,
                graph=graph,
            )
        except Exception as e:
            return AutonomousFixResult(
                mode=FixMode.PATCH,
                status="failed",
                request=request,
                phase="patch",
                plan=plan,
                errors=[f"Patch generation failed: {str(e)}"],
                message=f"Patch generation failed: {str(e)}",
            )

        # 3. Validate Patch
        validation = self.validator.validate(proposal.patch_diff)
        self.patch_service.save_latest_patch(proposal.to_dict())

        if not validation.is_valid:
            return AutonomousFixResult(
                mode=FixMode.PATCH,
                status="failed",
                request=request,
                phase="validate",
                plan=plan,
                proposal=proposal,
                validation=validation,
                errors=validation.errors,
                warnings=validation.warnings,
                message="Generated patch failed validation.",
            )

        return AutonomousFixResult(
            mode=FixMode.PATCH,
            status="patch_only",
            request=request,
            phase="validate",
            plan=plan,
            proposal=proposal,
            validation=validation,
            warnings=validation.warnings,
            message="Proposed patch generated and validated successfully. Not applied in PATCH mode.",
        )

    def _execute_auto_mode(
        self,
        request: str,
        force: bool = False,
        graph: Optional[GraphStore] = None,
        llm: Optional[Any] = None,
    ) -> AutonomousFixResult:
        """Executes full AUTO mode."""
        # 1. Safety Check: Verify Working Tree state
        try:
            repo = GitRepository(self.project_root)
            status_summary = self.reviewer.get_status_summary(repo)
            if not status_summary.is_clean and not force:
                dirty_details = []
                if status_summary.modified_files:
                    dirty_details.append(f"{len(status_summary.modified_files)} modified file(s)")
                if status_summary.untracked_files:
                    dirty_details.append(f"{len(status_summary.untracked_files)} untracked file(s)")
                if status_summary.staged_files:
                    dirty_details.append(f"{len(status_summary.staged_files)} staged file(s)")

                reason = f"Working tree contains uncommitted user modifications ({', '.join(dirty_details)}). Refusing autonomous modification to prevent data loss."
                return AutonomousFixResult(
                    mode=FixMode.AUTO,
                    status="refused_dirty_tree",
                    request=request,
                    phase="analyze",
                    errors=[reason],
                    warnings=["Commit or stash existing modifications before running AUTO mode, or pass force=True."],
                    message=reason,
                )
        except NotAGitRepositoryError:
            pass  # If not a git repo, proceed with caution

        # 2. Analyze & Plan
        try:
            plan = self.planner.plan_change(change_request=request, graph=graph)
        except Exception as e:
            return AutonomousFixResult(
                mode=FixMode.AUTO,
                status="failed",
                request=request,
                phase="plan",
                errors=[f"Planning failed: {str(e)}"],
                message=f"Planning failed: {str(e)}",
            )

        # 3. Patch Generation
        try:
            proposal = self.patch_generator.generate_patch(
                change_request=request,
                graph=graph,
            )
        except Exception as e:
            return AutonomousFixResult(
                mode=FixMode.AUTO,
                status="failed",
                request=request,
                phase="patch",
                plan=plan,
                errors=[f"Patch generation failed: {str(e)}"],
                message=f"Patch generation failed: {str(e)}",
            )

        # 4. Patch Validation
        validation = self.validator.validate(proposal.patch_diff)
        self.patch_service.save_latest_patch(proposal.to_dict())

        if not validation.is_valid:
            return AutonomousFixResult(
                mode=FixMode.AUTO,
                status="failed",
                request=request,
                phase="validate",
                plan=plan,
                proposal=proposal,
                validation=validation,
                errors=validation.errors,
                warnings=validation.warnings,
                message="Patch validation failed. No changes applied.",
            )

        # 5. Create Pre-Apply Rollback Checkpoint
        checkpoint_id = self.rollback_manager.create_checkpoint(files=validation.affected_files)

        # 6. Apply Patch
        try:
            self.applier.apply_patch(proposal.patch_diff)
        except Exception as e:
            rollback_res = self.rollback_manager.restore_checkpoint(checkpoint_id)
            return AutonomousFixResult(
                mode=FixMode.AUTO,
                status="failed",
                request=request,
                phase="apply",
                plan=plan,
                proposal=proposal,
                validation=validation,
                applied=False,
                rollback=rollback_res,
                errors=[f"Failed to apply patch: {str(e)}"],
                message=f"Failed to apply patch: {str(e)}. Restored repository backup.",
            )

        # 7. Post-Apply Test Execution
        test_targets = [t.split(" (")[0] for t in plan.relevant_tests if t.endswith(".py") or "tests/" in t]
        test_res = self.test_runner.run_tests(test_targets=test_targets if test_targets else None)

        if not test_res.is_success:
            # 8. Automatic Atomic Rollback on Test Failure
            rollback_res = self.rollback_manager.restore_checkpoint(checkpoint_id)
            err_msg = f"Post-apply tests failed with exit code {test_res.exit_code}."
            if test_res.output:
                err_msg += f" Details: {test_res.output[:400]}"

            return AutonomousFixResult(
                mode=FixMode.AUTO,
                status="rolled_back",
                request=request,
                phase="rollback",
                plan=plan,
                proposal=proposal,
                validation=validation,
                applied=True,
                test_result=test_res,
                rollback=rollback_res,
                errors=[err_msg],
                message="Tests failed following patch application. Changes were automatically rolled back.",
            )

        # 9. Post-Apply Intelligent Change Review
        try:
            review = self.reviewer.review_working_tree(graph=graph)
        except Exception:
            review = None

        # 10. Success: Keep Changes
        return AutonomousFixResult(
            mode=FixMode.AUTO,
            status="success",
            request=request,
            phase="complete",
            plan=plan,
            proposal=proposal,
            validation=validation,
            applied=True,
            test_result=test_res,
            review=review,
            message="Autonomous code fix applied, tested, and verified successfully. Changes kept in working tree.",
        )


# Architectural alias
FixOrchestrator = AutonomousFixService
