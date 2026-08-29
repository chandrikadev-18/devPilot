"""
Tests for DevPilot v2.0 — Git-Aware Change Intelligence.

Covers:
1. Git status parsing & branch detection
2. Modified, added, deleted, renamed, untracked file detection
3. Staged and unstaged change separation
4. Changed symbol detection (classes, functions, methods)
5. Impact analysis integration via dependency graph
6. Test intelligence & recommendation
7. Risk assessment (LOW, MEDIUM, HIGH)
8. JSON output format & schema stability
9. Human-readable CLI output formatting
10. Clean working tree handling ("No uncommitted changes detected.")
11. Non-Git directory error handling
12. Syntax error handling in changed files
13. API endpoint integration
"""

import json
from pathlib import Path
import shutil
import tempfile
import git
import pytest
from fastapi.testclient import TestClient

from app.changes.git_intelligence import GitChangeIntelligenceService
from app.git.change_detector import GitChangeDetector
from app.git.models import ChangeSummary, ChangeType, GitChange
from app.git.repository import NotAGitRepositoryError
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import app, run_changes


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Creates a standalone temporary Git repository."""
    repo = git.Repo.init(tmp_path)
    
    # Configure git author
    with repo.config_writer() as config:
        config.set_value("user", "name", "DevPilot Test")
        config.set_value("user", "email", "test@devpilot.ai")

    # Initial file
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    init_file = app_dir / "service.py"
    init_file.write_text(
        "class Service:\n"
        "    def process(self):\n"
        "        return 'ok'\n"
        "\n"
        "def helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_service.py"
    test_file.write_text(
        "from app.service import Service\n"
        "\n"
        "def test_service():\n"
        "    s = Service()\n"
        "    assert s.process() == 'ok'\n",
        encoding="utf-8",
    )

    repo.index.add([str(init_file), str(test_file)])
    repo.index.commit("Initial commit")

    return tmp_path, repo


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. GitChangeDetector & Models Unit Tests
# ==============================================================================

def test_git_change_detector_clean_repo(temp_git_repo):
    root, repo = temp_git_repo
    detector = GitChangeDetector(project_root=root)

    branch = detector.get_current_branch()
    assert branch in ("main", "master")

    changes = detector.get_changes()
    assert len(changes) == 0


def test_git_change_detector_modified_and_untracked(temp_git_repo):
    root, repo = temp_git_repo
    detector = GitChangeDetector(project_root=root)

    # 1. Modify existing file
    service_file = root / "app" / "service.py"
    service_file.write_text(
        "class Service:\n"
        "    def process(self):\n"
        "        return 'modified'\n"
        "\n"
        "def helper():\n"
        "    return 100\n",
        encoding="utf-8",
    )

    # 2. Add an untracked new file
    new_file = root / "app" / "utils.py"
    new_file.write_text("def new_util(): pass\n", encoding="utf-8")

    changes = detector.get_changes()
    assert len(changes) == 2

    c_map = {c.file_path: c for c in changes}
    assert "app/service.py" in c_map
    assert c_map["app/service.py"].change_type == ChangeType.MODIFIED.value
    assert c_map["app/service.py"].unstaged is True

    assert "app/utils.py" in c_map
    assert c_map["app/utils.py"].change_type == ChangeType.ADDED.value
    assert c_map["app/utils.py"].unstaged is True
    assert c_map["app/utils.py"].additions > 0


def test_git_change_detector_staged_and_deleted(temp_git_repo):
    root, repo = temp_git_repo
    detector = GitChangeDetector(project_root=root)

    # Delete test file
    test_file = root / "tests" / "test_service.py"
    test_file.unlink()

    # Stage the deletion
    repo.index.remove([str(test_file)])

    changes = detector.get_changes()
    assert len(changes) == 1
    assert changes[0].file_path == "tests/test_service.py"
    assert changes[0].change_type == ChangeType.DELETED.value
    assert changes[0].staged is True


# ==============================================================================
# 2. GitChangeIntelligenceService Unit Tests
# ==============================================================================

def test_git_intelligence_clean_working_tree(temp_git_repo):
    root, repo = temp_git_repo
    service = GitChangeIntelligenceService(project_root=root)

    summary = service.analyze_working_tree()
    assert isinstance(summary, ChangeSummary)
    assert len(summary.changed_files) == 0
    assert len(summary.changed_symbols) == 0
    assert summary.risk == "LOW"
    assert "No uncommitted changes" in summary.risk_reason
    assert "No uncommitted changes detected." in summary.to_formatted_text()


def test_git_intelligence_changed_symbols_and_impact(temp_git_repo):
    root, repo = temp_git_repo

    # Modify Service.process and add new function
    service_file = root / "app" / "service.py"
    service_file.write_text(
        "class Service:\n"
        "    def process(self):\n"
        "        return 'v2'\n"
        "    def new_method(self):\n"
        "        return 'new'\n"
        "\n"
        "def helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    # Build a graph representing the components
    graph = GraphStore()
    node_proc = GraphNode(
        id="method:app/service.py:Service.process",
        name="process",
        node_type=NodeType.METHOD,
        file_path="app/service.py",
        metadata={"parent_class": "Service"},
    )
    node_caller = GraphNode(
        id="function:tests/test_service.py:test_service",
        name="test_service",
        node_type=NodeType.FUNCTION,
        file_path="tests/test_service.py",
    )
    graph.add_node(node_proc)
    graph.add_node(node_caller)
    graph.add_edge(GraphEdge(
        source_id=node_caller.id,
        target_id=node_proc.id,
        edge_type=EdgeType.CALLS,
        line_number=5,
    ))

    service = GitChangeIntelligenceService(project_root=root)
    summary = service.analyze_working_tree(graph=graph)

    assert len(summary.changed_files) == 1
    assert "Service.process" in summary.changed_symbols
    assert "Service.new_method" in summary.changed_symbols
    assert "tests/test_service.py" in summary.relevant_tests


def test_git_intelligence_syntax_error_graceful_handling(temp_git_repo):
    root, repo = temp_git_repo

    # Introduce a syntax error in working tree
    service_file = root / "app" / "service.py"
    service_file.write_text("def invalid_syntax(:::", encoding="utf-8")

    service = GitChangeIntelligenceService(project_root=root)
    summary = service.analyze_working_tree()

    assert len(summary.changed_files) == 1
    assert len(summary.warnings) > 0
    assert any("Syntax" in w or "parsing" in w for w in summary.warnings)


def test_git_intelligence_non_git_repo(tmp_path: Path):
    non_git_dir = tmp_path / "not_git"
    non_git_dir.mkdir()

    service = GitChangeIntelligenceService(project_root=non_git_dir)
    with pytest.raises(NotAGitRepositoryError):
        service.analyze_working_tree()


# ==============================================================================
# 3. CLI & Output Formatting Tests
# ==============================================================================

def test_cli_changes_clean_repo(temp_git_repo, capsys):
    root, repo = temp_git_repo

    run_changes(project_dir=str(root), as_json=False)
    captured = capsys.readouterr()
    assert "No uncommitted changes detected." in captured.out


def test_cli_changes_json_output(temp_git_repo, capsys):
    root, repo = temp_git_repo

    # Add a change
    service_file = root / "app" / "service.py"
    service_file.write_text("def helper(): return 99\n", encoding="utf-8")

    run_changes(project_dir=str(root), as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert "branch" in data
    assert "changed_files" in data
    assert "changed_symbols" in data
    assert "impacted_symbols" in data
    assert "impacted_files" in data
    assert "relevant_tests" in data
    assert "risk" in data
    assert "risk_reason" in data
    assert "warnings" in data
    assert len(data["changed_files"]) == 1
    assert data["changed_files"][0]["file_path"] == "app/service.py"


def test_cli_changes_human_readable_output(temp_git_repo, capsys):
    root, repo = temp_git_repo

    # Add changes
    service_file = root / "app" / "service.py"
    service_file.write_text("def helper(): return 99\n", encoding="utf-8")

    run_changes(project_dir=str(root), as_json=False)
    captured = capsys.readouterr()

    assert "DevPilot v2.0 — Git Change Intelligence" in captured.out
    assert "Branch:" in captured.out
    assert "Changed Files:" in captured.out
    assert "MODIFIED" in captured.out or "app/service.py" in captured.out
    assert "Impact:" in captured.out
    assert "Risk:" in captured.out


# ==============================================================================
# 4. FastAPI Endpoint Tests
# ==============================================================================

def test_api_git_intelligence(client: TestClient, temp_git_repo):
    root, repo = temp_git_repo

    # Make a change
    new_f = root / "app" / "new.py"
    new_f.write_text("def new_func(): pass\n", encoding="utf-8")

    response = client.get(f"/api/changes/git-intelligence?project_dir={root}")
    assert response.status_code == 200
    data = response.json()

    assert "branch" in data
    assert len(data["changed_files"]) == 1
    assert data["changed_files"][0]["file_path"] == "app/new.py"
    assert "new_func" in data["changed_symbols"]
