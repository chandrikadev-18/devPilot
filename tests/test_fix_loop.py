"""
Tests for DevPilot v2.3 — Git-Aware Autonomous Fix Loop.
Verifies failure analysis, iterative repairs, max iteration limits,
safe rollbacks, working tree preservation, CLI commands, and REST API endpoints.
"""

import json
from pathlib import Path
import subprocess
import pytest
from starlette.testclient import TestClient

from app.changes.approval import ApprovalService
from app.changes.executor import ChangeExecutor
from app.changes.failure_analyzer import FailureAnalyzer
from app.changes.fix_loop import FixLoopService
from app.changes.models import (
    ChangeExecution,
    ChangeProposal,
    ExecutionStatus,
    FailureAnalysis,
    FixIteration,
    FixIterationStatus,
    FixLoopResult,
    ProposalStatus,
    TestValidationResult,
)
from app.changes.proposal_generator import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore, compute_file_hash, generate_proposal_id
from app.main import app, run_fix_loop


@pytest.fixture
def temp_codebase(tmp_path: Path) -> Path:
    """Sets up a clean temporary Git repository for testing fix loop."""
    app_dir = tmp_path / "app" / "graph"
    app_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    builder_file = app_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self, project_path: str):\n"
        "        \"\"\"Build graph store.\"\"\"\n"
        "        return True\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_builder.py"
    test_file.write_text(
        "from app.graph.builder import GraphBuilder\n\n"
        "def test_graph_builder():\n"
        "    builder = GraphBuilder()\n"
        "    assert builder.build('.') is True\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(tmp_path), capture_output=True, check=True)

    return tmp_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Failure Analyzer Unit Tests
# ==============================================================================

def test_failure_analyzer_extracts_failed_tests():
    analyzer = FailureAnalyzer()
    raw_output = (
        "============================= FAILURES =============================\n"
        "_____________________ test_api_execute_proposal _____________________\n"
        "tests/test_change_execution.py::test_api_execute_proposal FAILED [ 88%]\n"
        "E   AssertionError: assert 404 == 200\n"
    )
    analysis = analyzer.analyze(output_or_error=raw_output)

    assert "test_api_execute_proposal" in analysis.failed_tests or "tests/test_change_execution.py::test_api_execute_proposal" in analysis.failed_tests
    assert analysis.error_type == "AssertionError"
    assert "404 == 200" in analysis.error_message


def test_failure_analyzer_extracts_syntax_and_indentation_errors():
    analyzer = FailureAnalyzer()
    raw_error = "Syntax validation failed in 'app/graph/builder.py': unexpected indent (line 39)"
    analysis = analyzer.analyze(output_or_error=raw_error)

    assert analysis.error_type == "SyntaxError"
    assert "unexpected indent" in analysis.error_message
    assert "app/graph/builder.py" in analysis.affected_files
    assert analysis.confidence >= 0.9
    assert "Fix indentation" in analysis.suggested_fix_direction


def test_failure_analyzer_extracts_import_errors():
    analyzer = FailureAnalyzer()
    raw_output = (
        "============================= FAILURES =============================\n"
        "E   ModuleNotFoundError: No module named 'nonexistent_module'\n"
    )
    analysis = analyzer.analyze(output_or_error=raw_output)

    assert analysis.error_type == "ModuleNotFoundError"
    assert "nonexistent_module" in analysis.error_message
    assert "import" in analysis.suggested_fix_direction.lower()


def test_failure_analyzer_extracts_traceback():
    analyzer = FailureAnalyzer()
    raw_output = (
        "Traceback (most recent call last):\n"
        "  File \"app/graph/builder.py\", line 10, in build\n"
        "    return 1 / 0\n"
        "ZeroDivisionError: division by zero\n"
    )
    analysis = analyzer.analyze(output_or_error=raw_output)

    assert "Traceback" in analysis.traceback
    assert "ZeroDivisionError" in analysis.traceback or analysis.error_type in ("ZeroDivisionError", "UnknownError")


# ==============================================================================
# 2. Autonomous Fix Loop Execution & Retries Tests
# ==============================================================================

def test_fix_loop_plan_mode_never_modifies_files(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)
    result = service.fix(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="plan",
        max_iterations=3,
    )

    assert result.status == "PLAN_ONLY"
    assert result.mode == "plan"
    assert len(result.iterations) == 1
    assert result.iterations[0].status == FixIterationStatus.PROPOSED.value

    # Verify target file is completely untouched
    target_file = temp_codebase / "app" / "graph" / "builder.py"
    assert "import logging" not in target_file.read_text(encoding="utf-8")


def test_fix_loop_successful_first_execution(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)
    valid_patch = (
        "--- a/app/graph/builder.py\n"
        "+++ b/app/graph/builder.py\n"
        "@@ -1,4 +1,6 @@\n"
        " class GraphBuilder:\n"
        "     def build(self, project_path: str):\n"
        "+        # Valid harmless addition\n"
        "+        pass\n"
        "         \"\"\"Build graph store.\"\"\"\n"
        "         return True\n"
    )

    store = ProposalStore(project_root=temp_codebase)
    proposal = ChangeProposal(
        request="Add pass statement to GraphBuilder.build",
        proposal_id=generate_proposal_id(),
        target_symbol="GraphBuilder.build",
        target_file="app/graph/builder.py",
        target_lines="1-4",
        change_summary="Add harmless pass statement",
        affected_files=["app/graph/builder.py"],
        affected_symbols=["GraphBuilder.build"],
        proposed_changes=["Add pass"],
        patch=valid_patch,
        tests_to_update=[],
        tests_to_add=[],
        risk="LOW",
        reasoning="Low risk change",
        confidence=1.0,
        status=ProposalStatus.PENDING_APPROVAL.value,
        target_content_hash=compute_file_hash(temp_codebase / "app" / "graph" / "builder.py"),
    )
    store.save(proposal)

    result = service.fix(
        request="Add pass statement to GraphBuilder.build",
        mode="execute",
        max_iterations=3,
        proposal_id=proposal.proposal_id,
    )

    assert result.status == "SUCCESS"
    assert result.current_iteration == 1
    assert len(result.iterations) == 1
    assert result.iterations[0].status == FixIterationStatus.SUCCESS.value
    assert result.final_result is not None
    assert result.final_result.status == ExecutionStatus.SUCCESS.value


def test_fix_loop_iterative_repair_from_syntax_failure(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)

    # Initial broken patch with invalid indentation
    broken_patch = (
        "--- a/app/graph/builder.py\n"
        "+++ b/app/graph/builder.py\n"
        "@@ -1,4 +1,5 @@\n"
        " class GraphBuilder:\n"
        "     def build(self, project_path: str):\n"
        "+  bad_indentation = True\n"
        "         \"\"\"Build graph store.\"\"\"\n"
        "         return True\n"
    )

    store = ProposalStore(project_root=temp_codebase)
    proposal = ChangeProposal(
        request="Add logging when GraphBuilder.build starts and finishes",
        proposal_id=generate_proposal_id(),
        target_symbol="GraphBuilder.build",
        target_file="app/graph/builder.py",
        target_lines="1-4",
        change_summary="Add logging with bad indent initial patch",
        affected_files=["app/graph/builder.py"],
        affected_symbols=["GraphBuilder.build"],
        proposed_changes=["Add logging"],
        patch=broken_patch,
        tests_to_update=[],
        tests_to_add=[],
        risk="LOW",
        reasoning="Initial attempt",
        confidence=1.0,
        status=ProposalStatus.PENDING_APPROVAL.value,
        target_content_hash=compute_file_hash(temp_codebase / "app" / "graph" / "builder.py"),
    )
    store.save(proposal)

    result = service.fix(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="execute",
        max_iterations=3,
        proposal_id=proposal.proposal_id,
    )

    assert result.status == "SUCCESS"
    assert len(result.iterations) == 2
    # Iteration 1 failed due to syntax error and was diagnosed
    assert result.iterations[0].status == FixIterationStatus.FAILED.value
    assert result.iterations[0].failure_analysis is not None
    assert result.iterations[0].failure_analysis.error_type == "SyntaxError"

    # Iteration 2 succeeded with repaired patch
    assert result.iterations[1].status == FixIterationStatus.SUCCESS.value


def test_fix_loop_stops_after_max_iterations_and_rolls_back(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)

    # Patch that will always fail
    unfixable_patch = (
        "--- a/app/graph/builder.py\n"
        "+++ b/app/graph/builder.py\n"
        "@@ -1,4 +1,5 @@\n"
        " class GraphBuilder:\n"
        "     def build(self, project_path: str):\n"
        "+        raise RuntimeError('Permanent failure')\n"
        "         \"\"\"Build graph store.\"\"\"\n"
        "         return True\n"
    )

    store = ProposalStore(project_root=temp_codebase)
    proposal = ChangeProposal(
        request="Modify build to raise error",
        proposal_id=generate_proposal_id(),
        target_symbol="GraphBuilder.build",
        target_file="app/graph/builder.py",
        target_lines="1-4",
        change_summary="Raise runtime error",
        affected_files=["app/graph/builder.py"],
        affected_symbols=["GraphBuilder.build"],
        proposed_changes=["Raise error"],
        patch=unfixable_patch,
        tests_to_update=[],
        tests_to_add=[],
        risk="LOW",
        reasoning="Test unfixable",
        confidence=1.0,
        status=ProposalStatus.PENDING_APPROVAL.value,
        target_content_hash=compute_file_hash(temp_codebase / "app" / "graph" / "builder.py"),
    )
    store.save(proposal)

    # Set max_iterations to 2
    result = service.fix(
        request="Modify build to raise error",
        mode="execute",
        max_iterations=2,
        proposal_id=proposal.proposal_id,
    )

    assert result.status == "FAILED"
    assert result.current_iteration == 2
    assert result.max_iterations == 2
    assert len(result.iterations) == 2
    assert result.rollback_status == "SUCCESS"

    # Verify repository was restored cleanly
    target_file = temp_codebase / "app" / "graph" / "builder.py"
    assert "raise RuntimeError" not in target_file.read_text(encoding="utf-8")


def test_fix_loop_preserves_unrelated_working_tree_files(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)

    unrelated_file = temp_codebase / "unrelated.txt"
    unrelated_file.write_text("user notes", encoding="utf-8")

    result = service.fix(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="execute",
        max_iterations=2,
        force=True,
    )

    # Unrelated file must remain completely intact
    assert unrelated_file.exists()
    assert unrelated_file.read_text(encoding="utf-8") == "user notes"


def test_fix_loop_aborts_on_dirty_working_tree_without_force(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)

    # Make working tree dirty
    dirty_file = temp_codebase / "app" / "graph" / "builder.py"
    dirty_file.write_text("# Uncommitted user edit\n" + dirty_file.read_text(encoding="utf-8"), encoding="utf-8")

    result = service.fix(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="execute",
        max_iterations=2,
        force=False,
    )

    assert result.status == "FAILED"
    assert "uncommitted" in result.errors[0].lower() or "dirty" in result.errors[0].lower()


# ==============================================================================
# 3. CLI Command Tests
# ==============================================================================

def test_cli_fix_loop_plan_mode(temp_codebase: Path, capsys):
    run_fix_loop(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="plan",
        project_dir=str(temp_codebase),
        as_json=False,
    )
    captured = capsys.readouterr()

    assert "DevPilot v2.3 — Autonomous Fix Loop" in captured.out
    assert "Mode: PLAN" in captured.out
    assert "PLAN_ONLY" in captured.out


def test_cli_fix_loop_json_output(temp_codebase: Path, capsys):
    run_fix_loop(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="plan",
        project_dir=str(temp_codebase),
        as_json=True,
    )
    captured = capsys.readouterr()

    data = json.loads(captured.out)
    assert data["mode"] == "plan"
    assert data["status"] == "PLAN_ONLY"
    assert len(data["iterations"]) == 1


# ==============================================================================
# 4. REST API Endpoint Tests
# ==============================================================================

def test_api_fix_loop_endpoint_plan_mode(client: TestClient, temp_codebase: Path):
    response = client.post(
        "/changes/fix-loop",
        json={
            "request": "Add logging when GraphBuilder.build starts and finishes",
            "mode": "plan",
            "max_iterations": 3,
            "project_dir": str(temp_codebase),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "plan"
    assert data["status"] == "PLAN_ONLY"
    assert len(data["iterations"]) == 1


def test_api_fix_loop_endpoint_execute_mode(client: TestClient, temp_codebase: Path):
    response = client.post(
        "/changes/fix-loop",
        json={
            "request": "Add logging when GraphBuilder.build starts and finishes",
            "mode": "execute",
            "max_iterations": 2,
            "force": True,
            "project_dir": str(temp_codebase),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "execute"
    assert data["status"] in ("SUCCESS", "FAILED")
    assert "iterations" in data


def test_failure_analyzer_handles_type_and_runtime_errors():
    analyzer = FailureAnalyzer()
    raw_output = "TypeError: build() missing 1 required positional argument: 'project_path'"
    analysis = analyzer.analyze(output_or_error=raw_output)

    assert analysis.error_type == "TypeError"
    assert "positional argument" in analysis.error_message
    assert analysis.confidence >= 0.7


def test_fix_loop_empty_request_rejected(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)
    result = service.fix(request="", mode="plan")

    assert result.status == "FAILED"
    assert "cannot be empty" in result.errors[0]


def test_fix_loop_result_serialization_and_formatting(temp_codebase: Path):
    service = FixLoopService(project_root=temp_codebase)
    result = service.fix(
        request="Add logging when GraphBuilder.build starts and finishes",
        mode="plan",
    )

    formatted = result.to_formatted_text()
    assert "DevPilot v2.3 — Autonomous Fix Loop" in formatted
    assert "PLAN_ONLY" in formatted

    d = result.to_dict()
    assert d["mode"] == "plan"
    assert len(d["iterations"]) == 1

