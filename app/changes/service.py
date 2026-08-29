"""
DevPilot Safe Patch Application, Validation & Rollback Service (v1.7).

Coordinates patch validation, user confirmation, backup snapshotting,
clean unified diff application, post-apply test execution, and atomic rollbacks.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.changes.models import (
    PatchApplicationResult,
    PatchValidationResult,
    RollbackResult,
    TestValidationResult,
)
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.rollback import RollbackManager
from app.changes.test_runner import TestRunner


class SafePatchService:
    """
    High-level service orchestrating safe patch application, dry-runs,
    post-apply test validation, and backup rollbacks.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        validator: Optional[PatchValidator] = None,
        applier: Optional[PatchApplier] = None,
        rollback_manager: Optional[RollbackManager] = None,
        test_runner: Optional[TestRunner] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.validator = validator or PatchValidator(project_root=self.project_root)
        self.applier = applier or PatchApplier(project_root=self.project_root)
        self.rollback_manager = rollback_manager or RollbackManager(project_root=self.project_root)
        self.test_runner = test_runner or TestRunner(project_root=self.project_root)
        self.patches_dir = self.project_root / "data" / "patches"

    def save_latest_patch(self, patch_dict: Dict[str, Any]) -> None:
        """Persists the latest proposed change patch to data/patches/latest.json."""
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        latest_file = self.patches_dir / "latest.json"
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(patch_dict, f, indent=2)

    def load_latest_patch(self) -> Optional[Dict[str, Any]]:
        """Loads the latest proposed change patch from data/patches/latest.json."""
        latest_file = self.patches_dir / "latest.json"
        if not latest_file.exists():
            return None
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def dry_run(self, patch_str: str) -> PatchValidationResult:
        """
        Validates a patch, detects additions/deletions, affected files,
        and checks for conflicts without modifying any files.
        """
        return self.validator.validate(patch_str)

    def apply_and_validate(
        self,
        patch_str: str,
        auto_confirm: bool = False,
        confirm_callback: Optional[Callable[[List[str]], bool]] = None,
        run_validation_tests: bool = True,
        test_targets: Optional[List[str]] = None,
        rollback_on_failure: bool = True,
        rollback_confirm_callback: Optional[Callable[[], bool]] = None,
    ) -> PatchApplicationResult:
        """
        Executes the safe patch application workflow:
        1. Validate patch
        2. Check for conflicts / uncommitted changes
        3. Request explicit user confirmation
        4. Capture pre-apply backup snapshot
        5. Apply patch
        6. Run post-apply validation tests
        7. Rollback if tests fail
        """
        # 1. Validate Patch
        val_result = self.validator.validate(patch_str)
        if not val_result.is_valid:
            return PatchApplicationResult(
                status="validation_failed",
                applied=False,
                files_changed=[],
                errors=val_result.errors,
                warnings=val_result.warnings,
            )

        affected_files = val_result.files_affected

        # 2. User Confirmation
        if not auto_confirm:
            if confirm_callback is not None:
                approved = confirm_callback(affected_files)
            else:
                # Default interactive terminal confirmation
                print("\nThe following files will be modified:\n")
                for f in affected_files:
                    print(f"  {f}")
                print()
                try:
                    choice = input("Do you want to apply this patch? [y/N]: ").strip().lower()
                    approved = choice in ("y", "yes")
                except (EOFError, KeyboardInterrupt):
                    approved = False

            if not approved:
                return PatchApplicationResult(
                    status="cancelled",
                    applied=False,
                    files_changed=[],
                    warnings=["Patch application cancelled by user."],
                )

        # 3. Create Backup Checkpoint BEFORE applying
        checkpoint_id = self.rollback_manager.create_checkpoint(affected_files)

        # 4. Apply Patch
        try:
            applied_files = self.applier.apply_patch(patch_str)
        except Exception as e:
            # Revert on apply failure
            self.rollback_manager.restore_checkpoint(checkpoint_id)
            return PatchApplicationResult(
                status="validation_failed",
                applied=False,
                files_changed=[],
                errors=[f"Error applying patch: {str(e)}"],
                warnings=val_result.warnings,
            )

        # 5. Post-Apply Validation (Tests)
        test_dict: Optional[Dict[str, Any]] = None
        if run_validation_tests:
            test_res = self.test_runner.run_tests(test_targets=test_targets)
            test_dict = test_res.to_dict()

            if not test_res.is_success:
                # Tests failed!
                should_rollback = True
                if rollback_confirm_callback is not None:
                    should_rollback = rollback_confirm_callback()
                elif not auto_confirm:
                    try:
                        print(f"\n⚠ Validation failed ({test_res.failed} failed, {test_res.passed} passed).\n")
                        print("DevPilot can rollback the applied changes.\n")
                        choice = input("Rollback changes? [Y/n]: ").strip().lower()
                        should_rollback = choice not in ("n", "no")
                    except (EOFError, KeyboardInterrupt):
                        should_rollback = True

                if should_rollback:
                    self.rollback_manager.restore_checkpoint(checkpoint_id)
                    return PatchApplicationResult(
                        status="rolled_back",
                        applied=False,
                        files_changed=applied_files,
                        tests=test_dict,
                        rollback_available=False,
                        checkpoint_id=checkpoint_id,
                        errors=[f"Validation tests failed ({test_res.failed} test(s) failed). Changes were rolled back."],
                        warnings=val_result.warnings,
                    )
                else:
                    return PatchApplicationResult(
                        status="tests_failed",
                        applied=True,
                        files_changed=applied_files,
                        tests=test_dict,
                        rollback_available=True,
                        checkpoint_id=checkpoint_id,
                        errors=[f"Validation tests failed ({test_res.failed} test(s) failed). Changes kept as requested."],
                        warnings=val_result.warnings,
                    )

        return PatchApplicationResult(
            status="success",
            applied=True,
            files_changed=applied_files,
            tests=test_dict,
            rollback_available=True,
            checkpoint_id=checkpoint_id,
            warnings=val_result.warnings,
        )

    def rollback(self, checkpoint_id: Optional[str] = None) -> RollbackResult:
        """Rolls back the most recent or specified DevPilot patch application."""
        return self.rollback_manager.restore_checkpoint(checkpoint_id)
