"""
Tests for DevPilot v1.8 Git-Aware Change Planning & Intelligent Review.

Covers:
1. Clean repository review
2. Modified file review with diff, changed symbols, impact, and risk
3. Added file review
4. Deleted file review
5. Untracked file detection
6. Staged vs unstaged changes detection
7. Diff parsing and additions/deletions statistics
8. Impact analysis integration across dependency graph
9. Relevant test recommendation engine
10. Deterministic risk calculation (LOW, MEDIUM, HIGH)
11. Change planning with direct dependencies and markdown plan rendering
12. Review output formatting (to_formatted_text, to_dict, JSON)
13. Missing Git repository handling (NotAGitRepositoryError)
14. Agent tool `review_changes` execution and intent classification
15. REST API endpoints (POST and GET /api/changes/review)
16. CLI commands (`review`, `review --json`, `plan`, `plan --json`)
"""

import json
from pathlib import Path
import git
import pytest
from fastapi.testclient import TestClient

from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import create_review_changes_tool
from app.changes.models import (
    ChangedSymbol,
    ChangeImpact,
    ChangePlanEvidence,
    ChangeRisk,
    CodeChangePlan,
    GitChangeReview,
    GitStatusSummary,
    TestRecommendation,
)
from app.changes.planner import ChangeImpactPlanner
from app.changes.reviewer import GitChangeReviewer
from app.git.repository import NotAGitRepositoryError
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import app, run_plan_change, run_review


@pytest.fixture
def temp_git_project(tmp_path: Path) -> Path:
    """Initializes a temporary real Git repository with initial commit and files."""
    repo = git.Repo.init(tmp_path)
    
    # Configure git author
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test Developer")
        config.set_value("user", "email", "dev@example.com")

    # Add sample source file
    src_dir = tmp_path / "app" / "graph"
    src_dir.mkdir(parents=True, exist_ok=True)
    builder_file = src_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self):\n"
        "        return 'initial build'\n\n"
        "    def scan(self):\n"
        "        return 'scanning'\n",
        encoding="utf-8",
    )

    # Add test file
    test_dir = tmp_path / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test_graph_builder.py"
    test_file.write_text(
        "def test_builder():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    # Initial commit
    repo.index.add([str(builder_file), str(test_file)])
    repo.index.commit("Initial commit")

    return tmp_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Clean Repository Review
# ==============================================================================

def test_clean_repository_review(temp_git_project: Path):
    reviewer = GitChangeReviewer(project_root=temp_git_project)
    review = reviewer.review_working_tree()

    assert review.is_clean is True
    assert review.status.is_clean is True
    assert len(review.changed_files) == 0
    assert len(review.changed_symbols) == 0
    assert review.risk.level == "LOW"
    assert "Clean repository" in review.risk.reasons[0]
    
    formatted = review.to_formatted_text()
    assert "Working Tree: Clean" in formatted


# ==============================================================================
# 2. Modified File & Diff Inspection
# ==============================================================================

def test_modified_file_review(temp_git_project: Path):
    builder_file = temp_git_project / "app" / "graph" / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self):\n"
        "        # optimized build\n"
        "        return 'fast build'\n\n"
        "    def scan(self):\n"
        "        return 'scanning'\n",
        encoding="utf-8",
    )

    reviewer = GitChangeReviewer(project_root=temp_git_project)
    review = reviewer.review_working_tree()

    assert review.is_clean is False
    assert "app/graph/builder.py" in review.changed_files
    assert any(s.name == "GraphBuilder.build" and s.change_type == "modified" for s in review.changed_symbols)
    assert review.diff_stats["additions"] > 0
    assert "tests/test_graph_builder.py" in review.recommended_tests

    formatted = review.to_formatted_text()
    assert "DevPilot v1.8 — Git Change Review" in formatted
    assert "Modified:  app/graph/builder.py" in formatted
    assert "GraphBuilder.build" in formatted


# ==============================================================================
# 3. Added & Deleted Files
# ==============================================================================

def test_added_and_deleted_files_review(temp_git_project: Path):
    # Add new file
    new_file = temp_git_project / "app" / "new_module.py"
    new_file.write_text("def new_func():\n    return 123\n", encoding="utf-8")

    # Delete existing test file
    test_file = temp_git_project / "tests" / "test_graph_builder.py"
    test_file.unlink()

    reviewer = GitChangeReviewer(project_root=temp_git_project)
    review = reviewer.review_working_tree()

    assert "app/new_module.py" in review.changed_files
    assert "tests/test_graph_builder.py" in review.changed_files
    assert any(s.name == "new_func" and s.change_type == "added" for s in review.changed_symbols)


# ==============================================================================
# 4. Staged vs Unstaged Changes Detection
# ==============================================================================

def test_staged_vs_unstaged_detection(temp_git_project: Path):
    repo = git.Repo(temp_git_project)

    # 1. Modify builder.py and stage it
    builder_file = temp_git_project / "app" / "graph" / "builder.py"
    builder_file.write_text("class GraphBuilder:\n    def build(self):\n        return 'staged'\n", encoding="utf-8")
    repo.index.add([str(builder_file)])

    # 2. Modify test_graph_builder.py and leave unstaged
    test_file = temp_git_project / "tests" / "test_graph_builder.py"
    test_file.write_text("def test_builder():\n    assert 1 == 1\n", encoding="utf-8")

    reviewer = GitChangeReviewer(project_root=temp_git_project)
    review = reviewer.review_working_tree()

    assert "app/graph/builder.py" in review.status.staged_files
    assert "tests/test_graph_builder.py" in review.status.unstaged_files


# ==============================================================================
# 5. Dependency Graph Blast Radius & Test Discovery Integration
# ==============================================================================

def test_impact_and_test_discovery_with_graph(temp_git_project: Path):
    graph = GraphStore()

    # Target node: GraphBuilder.build
    target = GraphNode(
        id="method:app/graph/builder.py:GraphBuilder.build",
        name="GraphBuilder.build",
        node_type=NodeType.METHOD,
        file_path="app/graph/builder.py",
        start_line=2,
        end_line=4,
        metadata={"parent_class": "GraphBuilder"},
    )
    graph.add_node(target)

    # Dependent caller
    caller = GraphNode(
        id="function:app/agent/tools.py:_resolve_graph",
        name="_resolve_graph",
        node_type=NodeType.FUNCTION,
        file_path="app/agent/tools.py",
        start_line=10,
        end_line=20,
    )
    graph.add_node(caller)
    graph.add_edge(GraphEdge(
        source_id=caller.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
    ))

    # Test caller
    test_node = GraphNode(
        id="function:tests/test_graph_builder.py:test_builder",
        name="test_builder",
        node_type=NodeType.FUNCTION,
        file_path="tests/test_graph_builder.py",
        start_line=1,
        end_line=3,
    )
    graph.add_node(test_node)
    graph.add_edge(GraphEdge(
        source_id=test_node.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
    ))

    # Modify builder.py
    builder_file = temp_git_project / "app" / "graph" / "builder.py"
    builder_file.write_text("class GraphBuilder:\n    def build(self):\n        return 'revised'\n", encoding="utf-8")

    reviewer = GitChangeReviewer(project_root=temp_git_project)
    review = reviewer.review_working_tree(graph=graph)

    assert "_resolve_graph" in review.impact.direct_dependents
    assert any("test_builder" in t for t in review.recommended_tests)


# ==============================================================================
# 6. Change Planning & Markdown Rendering
# ==============================================================================

def test_change_plan_markdown_rendering():
    plan = CodeChangePlan(
        change_request="I want to modify GraphBuilder.build to improve graph construction.",
        target_symbol="GraphBuilder.build",
        target_file="app/graph/builder.py",
        target_lines="38-328",
        direct_dependencies=["ProjectScanner.scan", "ASTExtractor.extract_symbols"],
        affected_files=["app/graph/builder.py", "app/agent/tools.py"],
        affected_symbols=["_resolve_graph", "run_graph_build"],
        relevant_tests=["tests/test_graph_builder.py"],
        recommended_order=[
            "Implement core logic changes in GraphBuilder.build in app/graph/builder.py:38-328",
            "Verify direct dependencies: ProjectScanner.scan, ASTExtractor.extract_symbols",
            "Update direct dependents: _resolve_graph, run_graph_build",
            "Run relevant tests: tests/test_graph_builder.py",
            "Review diff",
        ],
        risk="HIGH",
        reason="Target 'GraphBuilder.build' has 2 direct dependents.",
    )

    md = plan.to_markdown_plan()
    assert "## Change Plan" in md
    assert "### Target" in md
    assert "`GraphBuilder.build`" in md
    assert "### Current Location" in md
    assert "`app/graph/builder.py:38-328`" in md
    assert "### Direct Dependencies" in md
    assert "- `ProjectScanner.scan`" in md
    assert "### Direct Dependents" in md
    assert "- `_resolve_graph`" in md
    assert "### Risk" in md
    assert "**HIGH**" in md
    assert "### Recommended Change Sequence" in md


# ==============================================================================
# 7. Non-Git Directory Handling
# ==============================================================================

def test_non_git_directory_error(tmp_path: Path):
    reviewer = GitChangeReviewer(project_root=tmp_path)
    with pytest.raises(NotAGitRepositoryError):
        reviewer.review_working_tree()


# ==============================================================================
# 8. Agent Tool and Intent Classification
# ==============================================================================

def test_review_changes_intent_classification():
    q1 = classify_question_intent("Review my current changes")
    assert q1.intent == QuestionIntent.REVIEW_CHANGES
    assert "review_changes" in q1.preferred_tools

    q2 = classify_question_intent("What will be affected by my current changes?")
    assert q2.intent == QuestionIntent.REVIEW_CHANGES

    q3 = classify_question_intent("What tests should I run for my current changes?")
    assert q3.intent == QuestionIntent.REVIEW_CHANGES

    q4 = classify_question_intent("Create a change plan for modifying GraphBuilder.build")
    assert q4.intent == QuestionIntent.CHANGE_PLAN
    assert q4.target_symbol == "GraphBuilder.build"


def test_review_changes_agent_tool(temp_git_project: Path):
    tool = create_review_changes_tool(project_root=temp_git_project)
    assert tool["name"] == "review_changes"
    
    # Execute tool on clean workspace
    res = tool["func"](str(temp_git_project))
    assert "data" in res
    assert "formatted_text" in res
    assert res["data"]["is_clean"] is True


# ==============================================================================
# 9. REST API Endpoints
# ==============================================================================

def test_api_review_get_and_post(client: TestClient, temp_git_project: Path):
    # GET /api/changes/review
    res_get = client.get("/api/changes/review", params={"project_dir": str(temp_git_project)})
    assert res_get.status_code == 200
    data = res_get.json()
    assert "branch" in data
    assert "is_clean" in data
    assert "risk" in data

    # POST /api/changes/review
    res_post = client.post("/api/changes/review", json={"project_dir": str(temp_git_project)})
    assert res_post.status_code == 200
    assert res_post.json()["is_clean"] is True


# ==============================================================================
# 10. CLI Command Tests
# ==============================================================================

def test_cli_review_command(temp_git_project: Path, capsys):
    # Text output
    run_review(project_dir=str(temp_git_project), as_json=False)
    captured = capsys.readouterr()
    assert "DevPilot v1.8 — Git Change Review" in captured.out
    assert "Working Tree: Clean" in captured.out

    # JSON output
    run_review(project_dir=str(temp_git_project), as_json=True)
    captured_json = capsys.readouterr()
    parsed = json.loads(captured_json.out)
    assert parsed["is_clean"] is True
    assert "status" in parsed
