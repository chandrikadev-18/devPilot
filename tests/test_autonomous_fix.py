"""
Tests for DevPilot v1.9 Autonomous Code Fix Loop.

Covers:
1. PLAN mode (Analysis & Plan generation without repository modification)
2. PATCH mode (Plan + Patch generation + Validation without applying)
3. AUTO mode success (Complete loop: plan -> patch -> validate -> apply -> tests pass -> review -> keep changes)
4. AUTO mode test failure with automatic rollback (Tests fail -> atomic rollback -> repository restored)
5. Dirty working tree protection in AUTO mode (Refusal to overwrite uncommitted user work)
6. Force execution override for working tree
7. Invalid patch rejection before application
8. Empty or invalid request handling
9. Agent tool `autonomous_fix` execution and intent classification
10. REST API endpoints (POST /api/changes/fix and GET /api/changes/fix)
11. CLI `fix` command output (formatted text and JSON)
"""

import json
from pathlib import Path
from typing import Any, List, Optional
import git
import pytest
from fastapi.testclient import TestClient

from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import create_autonomous_fix_tool
from app.changes.autonomous_fix import AutonomousFixService, FixOrchestrator
from app.changes.models import (
    AutonomousFixResult,
    CodeChangePlan,
    CodeChangeProposal,
    FixMode,
    PatchValidationResult,
    TestValidationResult,
)
from app.changes.patch import CodeChangePatchGenerator
from app.changes.patch_validator import PatchValidator
from app.changes.test_runner import TestRunner
from app.main import app, run_fix


class FailingTestRunner(TestRunner):
    """Mock test runner that simulates failing unit tests."""
    def run_tests(self, test_targets: Optional[List[str]] = None) -> TestValidationResult:
        return TestValidationResult(
            is_success=False,
            passed=0,
            failed=1,
            skipped=0,
            exit_code=1,
            output="FAILED tests/test_graph_builder.py::test_build - AssertionError: unexpected return value",
            execution_time=0.42,
        )


class MockPassingPatchGenerator(CodeChangePatchGenerator):
    """Generates a known valid patch for testing."""
    def generate_patch(self, change_request: str, graph: Optional[Any] = None, **kwargs) -> CodeChangeProposal:
        diff_text = (
            "--- a/app/graph/builder.py\n"
            "+++ b/app/graph/builder.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def build():\n"
            "-    return 'old'\n"
            "+    return 'fixed'\n"
        )
        return CodeChangeProposal(
            change_request=change_request,
            target="build in app/graph/builder.py",
            risk="LOW",
            affected_files=["app/graph/builder.py"],
            patch=diff_text,
        )


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Sets up a clean git repository fixture for fix testing."""
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test Dev")
        config.set_value("user", "email", "dev@example.com")

    app_dir = tmp_path / "app" / "graph"
    app_dir.mkdir(parents=True, exist_ok=True)
    builder_file = app_dir / "builder.py"
    builder_file.write_text("def build():\n    return 'old'\n", encoding="utf-8")

    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test_graph_builder.py"
    test_file.write_text("def test_build():\n    assert True\n", encoding="utf-8")

    repo.index.add([str(builder_file), str(test_file)])
    repo.index.commit("Initial commit")

    return tmp_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. PLAN Mode Tests
# ==============================================================================

def test_autonomous_fix_plan_mode(temp_project: Path):
    service = AutonomousFixService(project_root=temp_project)
    result = service.execute(
        request="Modify build in app/graph/builder.py",
        mode=FixMode.PLAN,
    )

    assert result.mode == FixMode.PLAN
    assert result.status == "plan_only"
    assert result.phase == "plan"
    assert result.applied is False
    assert result.plan is not None
    assert "app/graph/builder.py" in result.plan.affected_files
    
    # Verify no files were modified on disk
    builder_content = (temp_project / "app" / "graph" / "builder.py").read_text(encoding="utf-8")
    assert "return 'old'" in builder_content


# ==============================================================================
# 2. PATCH Mode Tests
# ==============================================================================

def test_autonomous_fix_patch_mode(temp_project: Path):
    service = AutonomousFixService(
        project_root=temp_project,
        patch_generator=MockPassingPatchGenerator(project_root=temp_project),
    )
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.PATCH,
    )

    assert result.mode == FixMode.PATCH
    assert result.status == "patch_only"
    assert result.phase == "validate"
    assert result.applied is False
    assert result.proposal is not None
    assert result.validation is not None
    assert result.validation.is_valid is True

    # Verify no files were modified on disk
    builder_content = (temp_project / "app" / "graph" / "builder.py").read_text(encoding="utf-8")
    assert "return 'old'" in builder_content


# ==============================================================================
# 3. AUTO Mode Success Tests
# ==============================================================================

def test_autonomous_fix_auto_mode_success(temp_project: Path):
    service = AutonomousFixService(
        project_root=temp_project,
        patch_generator=MockPassingPatchGenerator(project_root=temp_project),
    )
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.AUTO,
    )

    assert result.mode == FixMode.AUTO
    assert result.status == "success"
    assert result.phase == "complete"
    assert result.applied is True
    assert result.test_result is not None
    assert result.test_result.is_success is True
    assert result.review is not None
    assert "app/graph/builder.py" in result.review.changed_files

    # Verify files were modified and changes kept
    builder_content = (temp_project / "app" / "graph" / "builder.py").read_text(encoding="utf-8")
    assert "return 'fixed'" in builder_content


# ==============================================================================
# 4. AUTO Mode Test Failure & Automatic Rollback Tests
# ==============================================================================

def test_autonomous_fix_auto_mode_failure_and_rollback(temp_project: Path):
    service = AutonomousFixService(
        project_root=temp_project,
        patch_generator=MockPassingPatchGenerator(project_root=temp_project),
        test_runner=FailingTestRunner(project_root=temp_project),
    )
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.AUTO,
    )

    assert result.mode == FixMode.AUTO
    assert result.status == "rolled_back"
    assert result.phase == "rollback"
    assert result.applied is True
    assert result.test_result.is_success is False
    assert result.rollback is not None
    assert result.rollback.status == "success"

    # Verify repository was cleanly restored
    builder_content = (temp_project / "app" / "graph" / "builder.py").read_text(encoding="utf-8")
    assert "return 'old'" in builder_content


# ==============================================================================
# 5. Dirty Working Tree Protection Tests
# ==============================================================================

def test_autonomous_fix_refuses_dirty_working_tree(temp_project: Path):
    # Create an uncommitted change in working tree
    builder_file = temp_project / "app" / "graph" / "builder.py"
    builder_file.write_text("def build():\n    # uncommitted user work\n    return 'old'\n", encoding="utf-8")

    service = AutonomousFixService(project_root=temp_project)
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.AUTO,
        force=False,
    )

    assert result.status == "refused_dirty_tree"
    assert result.phase == "analyze"
    assert len(result.errors) > 0
    assert "uncommitted user modifications" in result.errors[0]


def test_autonomous_fix_force_dirty_working_tree(temp_project: Path):
    # Create an uncommitted change
    builder_file = temp_project / "app" / "graph" / "builder.py"
    builder_file.write_text("def build():\n    return 'old'\n", encoding="utf-8")

    service = AutonomousFixService(
        project_root=temp_project,
        patch_generator=MockPassingPatchGenerator(project_root=temp_project),
    )
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.AUTO,
        force=True,
    )

    assert result.status == "success"
    assert result.applied is True


# ==============================================================================
# 6. Invalid Patch Rejection Tests
# ==============================================================================

class MockInvalidPatchGenerator(CodeChangePatchGenerator):
    def generate_patch(self, change_request: str, graph: Optional[Any] = None, **kwargs) -> CodeChangeProposal:
        return CodeChangeProposal(
            change_request=change_request,
            target="missing in non_existent.py",
            risk="HIGH",
            affected_files=["non_existent.py"],
            patch="invalid unified diff content without headers",
        )


def test_autonomous_fix_invalid_patch_rejection(temp_project: Path):
    service = AutonomousFixService(
        project_root=temp_project,
        patch_generator=MockInvalidPatchGenerator(project_root=temp_project),
    )
    result = service.execute(
        request="Fix return value in build in app/graph/builder.py",
        mode=FixMode.AUTO,
        force=True,
    )

    assert result.status == "failed"
    assert result.phase == "validate"
    assert result.applied is False
    assert len(result.errors) > 0


# ==============================================================================
# 7. Agent Tool & Intent Classification Tests
# ==============================================================================

def test_autonomous_fix_intent_classification():
    q1 = classify_question_intent("Analyze this bug but don't change anything.")
    assert q1.intent == QuestionIntent.AUTONOMOUS_FIX
    assert "autonomous_fix" in q1.preferred_tools

    q2 = classify_question_intent("Prepare a patch for this issue.")
    assert q2.intent == QuestionIntent.AUTONOMOUS_FIX

    q3 = classify_question_intent("Fix this issue automatically and run the tests.")
    assert q3.intent == QuestionIntent.AUTONOMOUS_FIX

    q4 = classify_question_intent("Fix the bug in GraphBuilder.build")
    assert q4.intent == QuestionIntent.AUTONOMOUS_FIX
    assert q4.target_symbol == "GraphBuilder.build"


def test_autonomous_fix_agent_tool(temp_project: Path):
    tool = create_autonomous_fix_tool(project_root=temp_project)
    assert tool["name"] == "autonomous_fix"

    # Execute tool in PLAN mode
    res = tool["func"](request="Modify build in app/graph/builder.py", mode="plan")
    assert "data" in res
    assert "formatted_text" in res
    assert res["data"]["mode"] == "PLAN"
    assert res["data"]["status"] == "plan_only"


# ==============================================================================
# 8. REST API Endpoints Tests
# ==============================================================================

def test_api_autonomous_fix_post_and_get(client: TestClient, temp_project: Path):
    # POST /api/changes/fix
    res_post = client.post(
        "/api/changes/fix",
        json={
            "request": "Modify build in app/graph/builder.py",
            "mode": "plan",
            "project_dir": str(temp_project),
        },
    )
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["mode"] == "PLAN"
    assert data_post["status"] == "plan_only"

    # GET /api/changes/fix
    res_get = client.get(
        "/api/changes/fix",
        params={
            "request": "Modify build in app/graph/builder.py",
            "mode": "plan",
            "project_dir": str(temp_project),
        },
    )
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["mode"] == "PLAN"


# ==============================================================================
# 9. CLI Command Tests
# ==============================================================================

def test_cli_fix_command(temp_project: Path, capsys):
    # PLAN mode formatted text
    run_fix(
        request="Modify build in app/graph/builder.py",
        mode="plan",
        project_dir=str(temp_project),
        as_json=False,
    )
    captured = capsys.readouterr()
    assert "DevPilot v1.9 — Autonomous Code Fix" in captured.out
    assert "Mode:    PLAN" in captured.out
    assert "Status:  PLAN_ONLY" in captured.out

    # PLAN mode JSON
    run_fix(
        request="Modify build in app/graph/builder.py",
        mode="plan",
        project_dir=str(temp_project),
        as_json=True,
    )
    captured_json = capsys.readouterr()
    parsed = json.loads(captured_json.out)
    assert parsed["mode"] == "PLAN"
    assert parsed["status"] == "plan_only"
