"""
Tests for DevPilot v1.6 AI Change Planner & Patch Generator.

Covers:
1. Valid change request & target identification
2. Affected files and symbols detection
3. Reviewable unified diff patch generation
4. JSON output formatting matching expected schema
5. Ambiguous / unverified target handling with warnings
6. Missing target / empty change request handling
7. Safety validation: verify no files on disk are modified
8. Regression validation against existing graph and plan-change functions
9. CLI invocation: run_change with text and json outputs
"""

import json
from pathlib import Path
import pytest

from app.changes.models import CodeChangeProposal, FileChangeItem
from app.changes.patch import CodeChangePatchGenerator
from app.changes.planner import ChangeImpactPlanner
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import run_change, run_plan_change


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def sample_graph() -> GraphStore:
    graph = GraphStore()
    target = GraphNode(
        id="method:app/graph/builder.py:GraphBuilder.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/graph/builder.py",
        start_line=38,
        end_line=328,
        metadata={"parent_class": "GraphBuilder"},
    )
    graph.add_node(target)

    caller = GraphNode(
        id="function:app/agent/tools.py:_resolve_graph",
        name="_resolve_graph",
        node_type=NodeType.FUNCTION,
        file_path="app/agent/tools.py",
        start_line=1540,
        end_line=1560,
    )
    graph.add_node(caller)
    graph.add_edge(GraphEdge(
        source_id=caller.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
        line_number=1545,
    ))

    test_caller = GraphNode(
        id="function:tests/test_graph_builder.py:test_build",
        name="test_build",
        node_type=NodeType.FUNCTION,
        file_path="tests/test_graph_builder.py",
        start_line=10,
        end_line=20,
    )
    graph.add_node(test_caller)
    graph.add_edge(GraphEdge(
        source_id=test_caller.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
        line_number=12,
    ))

    return graph


# ==============================================================================
# 1. Valid Change Request & Patch Generation Tests
# ==============================================================================

def test_valid_change_request_patch_generation(project_root: Path, sample_graph: GraphStore):
    target_file = project_root / "app/graph/builder.py"
    with open(target_file, "r", encoding="utf-8") as f:
        before_content = f.read()

    generator = CodeChangePatchGenerator(project_root=project_root)
    proposal = generator.generate_patch("Improve GraphBuilder.build performance", graph=sample_graph)

    # 1. Verify proposal structure
    assert proposal.change_request == "Improve GraphBuilder.build performance"
    assert "GraphBuilder.build" in proposal.target
    assert "app/graph/builder.py" in proposal.affected_files
    assert proposal.risk in ("LOW", "MEDIUM", "HIGH")
    assert len(proposal.patch) > 0
    assert "--- a/app/graph/builder.py" in proposal.patch or "--- a/" in proposal.patch
    assert "+++ b/app/graph/builder.py" in proposal.patch or "+++ b/" in proposal.patch
    assert len(proposal.changes) > 0
    assert proposal.changes[0].file == "app/graph/builder.py"
    assert len(proposal.tests_to_run) > 0
    assert len(proposal.warnings) == 0

    # 2. Safety Check: Verify target file on disk was NEVER modified
    with open(target_file, "r", encoding="utf-8") as f:
        after_content = f.read()
    assert before_content == after_content


# ==============================================================================
# 2. JSON Structure Matching Requirements
# ==============================================================================

def test_change_proposal_json_schema(project_root: Path, sample_graph: GraphStore):
    generator = CodeChangePatchGenerator(project_root=project_root)
    proposal = generator.generate_patch("Improve GraphBuilder.build performance", graph=sample_graph)
    data = proposal.to_dict()

    # Exact expected JSON fields
    expected_keys = {
        "change_request",
        "target",
        "risk",
        "affected_files",
        "affected_symbols",
        "changes",
        "patch",
        "tests_to_run",
        "warnings",
    }
    assert expected_keys.issubset(set(data.keys()))
    assert isinstance(data["affected_files"], list)
    assert isinstance(data["affected_symbols"], list)
    assert isinstance(data["changes"], list)
    assert isinstance(data["tests_to_run"], list)
    assert isinstance(data["warnings"], list)
    assert isinstance(data["patch"], str)


# ==============================================================================
# 3. Ambiguous / Unverified Target Handling
# ==============================================================================

def test_ambiguous_or_unverified_target(project_root: Path):
    generator = CodeChangePatchGenerator(project_root=project_root)
    proposal = generator.generate_patch("Refactor completely_fake_and_nonexistent_service_12345", graph=GraphStore())

    assert len(proposal.warnings) > 0
    assert "cannot be confidently identified" in proposal.warnings[0]
    assert proposal.patch == ""
    assert len(proposal.changes) == 0


def test_empty_change_request(project_root: Path):
    generator = CodeChangePatchGenerator(project_root=project_root)
    proposal = generator.generate_patch("")

    assert len(proposal.warnings) > 0
    assert "cannot be empty" in proposal.warnings[0]
    assert proposal.patch == ""


# ==============================================================================
# 4. Text Formatting and Human-Readable Summary
# ==============================================================================

def test_proposal_formatted_text():
    proposal = CodeChangeProposal(
        change_request="Improve GraphBuilder.build performance",
        target="GraphBuilder.build",
        risk="LOW",
        affected_files=["app/graph/builder.py"],
        affected_symbols=["_resolve_graph"],
        changes=[
            FileChangeItem(
                file="app/graph/builder.py",
                description="Optimized build method traversal",
                explanation="Reduces repeated AST parsing overhead",
            )
        ],
        patch="--- a/app/graph/builder.py\n+++ b/app/graph/builder.py\n@@ -38,3 +38,4 @@\n+    # optimized",
        tests_to_run=["tests/test_graph_builder.py"],
        warnings=[],
    )

    text = proposal.to_formatted_text()
    assert "Change Request:\nImprove GraphBuilder.build performance" in text
    assert "Target:\nGraphBuilder.build" in text
    assert "Risk:\nLOW" in text
    assert "Proposed Modifications:" in text
    assert "Proposed Patch (Unified Diff):" in text
    assert "Tests to Run:" in text
    assert "Warnings:" not in text


# ==============================================================================
# 5. CLI Command Tests (change)
# ==============================================================================

def test_cli_run_change_text(capsys):
    run_change(change_request="Improve GraphBuilder.build performance", as_json=False)
    captured = capsys.readouterr()
    assert "Change Request:" in captured.out
    assert "Target:" in captured.out
    assert "Risk:" in captured.out
    assert "Proposed Patch" in captured.out or "Proposed Modifications" in captured.out


def test_cli_run_change_json(capsys):
    run_change(change_request="Improve GraphBuilder.build performance", as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["change_request"] == "Improve GraphBuilder.build performance"
    assert "target" in data
    assert "risk" in data
    assert "affected_files" in data
    assert "changes" in data
    assert "patch" in data
    assert "tests_to_run" in data
    assert "warnings" in data


# ==============================================================================
# 6. Regression Against Existing Graph and Plan-Change Commands
# ==============================================================================

def test_plan_change_regression(capsys):
    run_plan_change(change_request="Improve GraphBuilder.build performance", as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["change_request"] == "Improve GraphBuilder.build performance"
    assert data["target"] == "GraphBuilder.build"
    assert "evidence" in data
    assert "recommended_order" in data
