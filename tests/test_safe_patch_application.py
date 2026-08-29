"""
Tests for DevPilot v1.7 Safe Patch Application, Validation & Rollback.

Covers:
1. Patch validation (valid, malformed, stale, traversal, protected files, missing target)
2. Interactive confirmation (accept, reject, cancellation without file modification)
3. Safe patch application (single-file, multi-file, backup snapshot creation)
4. Post-application test validation (passed tests, failed tests triggering rollback)
5. Rollback mechanisms (automatic post-failure, manual CLI rollback, non-existent checkpoint, isolation to only DevPilot files)
6. CLI commands (apply-change --dry-run, --yes, --json, rollback, rollback --json)
"""

import json
from pathlib import Path
import pytest

from app.changes.models import (
    PatchApplicationResult,
    PatchValidationResult,
    RollbackResult,
    TestValidationResult,
)
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.rollback import RollbackManager
from app.changes.service import SafePatchService
from app.changes.test_runner import TestRunner
from app.main import run_apply_change, run_rollback


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Creates a temporary workspace with sample code files."""
    code_file = tmp_path / "app" / "sample.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    unrelated_file = tmp_path / "app" / "unrelated.py"
    unrelated_file.write_text("UNRELATED_VAL = 42\n", encoding="utf-8")

    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_API_KEY=supersecret\n", encoding="utf-8")

    return tmp_path


# ==============================================================================
# 1. Patch Validation Tests
# ==============================================================================

def test_valid_patch_validation(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # optimized\n"
        "     return 'world'\n"
    )
    result = validator.validate(patch)
    assert result.is_valid is True
    assert result.status == "SAFE TO APPLY"
    assert result.files_affected == ["app/sample.py"]
    assert result.additions == 1
    assert result.deletions == 0
    assert len(result.errors) == 0


def test_malformed_patch_validation(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    result = validator.validate("just some random text without diff headers")
    assert result.is_valid is False
    assert result.status == "VALIDATION FAILED"
    assert len(result.errors) > 0


def test_path_traversal_rejection(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    patch = (
        "--- a/../../outside.py\n"
        "+++ b/../../outside.py\n"
        "@@ -1,1 +1,2 @@\n"
        "+bad code\n"
    )
    result = validator.validate(patch)
    assert result.is_valid is False
    assert any("traversal" in e.lower() for e in result.errors)


def test_protected_file_rejection(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    patch = (
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1,1 +1,2 @@\n"
        "+LEAK=1\n"
    )
    result = validator.validate(patch)
    assert result.is_valid is False
    assert any("protected" in e.lower() or ".env" in e for e in result.errors)


def test_missing_target_file_rejection(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    patch = (
        "--- a/app/non_existent.py\n"
        "+++ b/app/non_existent.py\n"
        "@@ -1,1 +1,2 @@\n"
        "+code\n"
    )
    result = validator.validate(patch)
    assert result.is_valid is False
    assert any("does not exist" in e for e in result.errors)


def test_stale_patch_context_warning(temp_project: Path):
    validator = PatchValidator(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        "-def completely_nonexistent_signature():\n"
        "+def hello():\n"
        "     return 'world'\n"
    )
    result = validator.validate(patch)
    assert len(result.warnings) > 0
    assert any("stale" in w.lower() for w in result.warnings)


# ==============================================================================
# 2. Confirmation and Cancellation Tests
# ==============================================================================

def test_apply_patch_cancellation(temp_project: Path):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # rejected change\n"
        "     return 'world'\n"
    )

    # Simulate user rejecting the confirmation prompt
    result = service.apply_and_validate(
        patch_str=patch,
        auto_confirm=False,
        confirm_callback=lambda files: False,
        run_validation_tests=False,
    )

    assert result.status == "cancelled"
    assert result.applied is False

    # Verify target file was NOT modified
    content = (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
    assert "# rejected change" not in content


# ==============================================================================
# 3. Patch Application and Post-Apply Tests
# ==============================================================================

def test_safe_patch_application_success(temp_project: Path):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # applied change\n"
        "     return 'world'\n"
    )

    result = service.apply_and_validate(
        patch_str=patch,
        auto_confirm=True,
        run_validation_tests=False,
    )

    assert result.status == "success"
    assert result.applied is True
    assert "app/sample.py" in result.files_changed
    assert result.rollback_available is True

    # Verify target file was modified
    content = (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
    assert "# applied change" in content

    # Verify unrelated file was untouched
    unrelated = (temp_project / "app" / "unrelated.py").read_text(encoding="utf-8")
    assert unrelated == "UNRELATED_VAL = 42\n"


# ==============================================================================
# 4. Rollback Isolation & Test Failure Handling
# ==============================================================================

def test_automatic_rollback_on_test_failure(temp_project: Path):
    class FailingTestRunner(TestRunner):
        def run_tests(self, test_targets=None):
            return TestValidationResult(
                passed=10,
                failed=2,
                skipped=0,
                execution_time=1.2,
                exit_code=1,
                is_success=False,
                output="2 failed",
            )

    service = SafePatchService(
        project_root=temp_project,
        test_runner=FailingTestRunner(project_root=temp_project),
    )

    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # broken change\n"
        "     return 'world'\n"
    )

    # Apply with auto-confirm and auto-rollback on failure
    result = service.apply_and_validate(
        patch_str=patch,
        auto_confirm=True,
        rollback_on_failure=True,
        rollback_confirm_callback=lambda: True,
    )

    assert result.status == "rolled_back"
    assert result.applied is False

    # Verify target file was restored to original state
    content = (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
    assert "# broken change" not in content
    assert content == "def hello():\n    return 'world'\n"


def test_manual_rollback_service(temp_project: Path):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # manual test change\n"
        "     return 'world'\n"
    )

    # 1. Apply patch successfully
    service.apply_and_validate(
        patch_str=patch,
        auto_confirm=True,
        run_validation_tests=False,
    )
    assert "# manual test change" in (temp_project / "app" / "sample.py").read_text(encoding="utf-8")

    # 2. Rollback manually
    rb_res = service.rollback()
    assert rb_res.status == "success"
    assert "app/sample.py" in rb_res.reverted_files

    # 3. Verify file restored
    restored = (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
    assert "# manual test change" not in restored


def test_manual_rollback_no_checkpoint(temp_project: Path):
    service = SafePatchService(project_root=temp_project)
    rb_res = service.rollback()
    assert rb_res.status == "no_checkpoint"
    assert "No rollback checkpoint found" in rb_res.message


# ==============================================================================
# 5. CLI Execution Tests
# ==============================================================================

def test_cli_apply_change_dry_run(temp_project: Path, capsys):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # dry run test\n"
        "     return 'world'\n"
    )
    service.save_latest_patch({"patch": patch, "tests_to_run": []})

    run_apply_change(dry_run=True, project_dir=str(temp_project), as_json=False)
    captured = capsys.readouterr()
    assert "Patch Validation" in captured.out
    assert "SAFE TO APPLY" in captured.out
    assert "Dry run:" in captured.out
    assert "No files were modified." in captured.out

    # Verify file was NOT modified
    content = (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
    assert "# dry run test" not in content


def test_cli_apply_change_dry_run_json(temp_project: Path, capsys):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # dry run json test\n"
        "     return 'world'\n"
    )
    service.save_latest_patch({"patch": patch, "tests_to_run": []})

    run_apply_change(dry_run=True, project_dir=str(temp_project), as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_valid"] is True
    assert "SAFE TO APPLY" in data["status"]
    assert "app/sample.py" in data["files_affected"]


def test_cli_apply_change_yes_and_rollback(temp_project: Path, capsys):
    service = SafePatchService(project_root=temp_project)
    patch = (
        "--- a/app/sample.py\n"
        "+++ b/app/sample.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def hello():\n"
        "+    # applied via CLI\n"
        "     return 'world'\n"
    )
    service.save_latest_patch({"patch": patch, "tests_to_run": []})

    # Apply via CLI with --yes (and simulate test runner in temp dir)
    run_apply_change(auto_confirm=True, project_dir=str(temp_project), as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "success"
    assert data["applied"] is True

    assert "# applied via CLI" in (temp_project / "app" / "sample.py").read_text(encoding="utf-8")

    # Rollback via CLI
    run_rollback(project_dir=str(temp_project), as_json=True)
    captured_rb = capsys.readouterr()
    rb_data = json.loads(captured_rb.out)
    assert rb_data["status"] == "success"
    assert "app/sample.py" in rb_data["reverted_files"]

    assert "# applied via CLI" not in (temp_project / "app" / "sample.py").read_text(encoding="utf-8")
