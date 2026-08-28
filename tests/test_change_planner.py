"""
Tests for DevPilot v1.7 Change Impact Planner.

Covers:
1. Known symbol change (e.g. GraphBuilder.build)
2. File-based change (e.g. app/graph/builder.py)
3. Semantic search fallback (when symbol is not directly found in graph)
4. Direct and indirect impact analysis
5. Relevant test discovery (graph callers + test files)
6. Deterministic risk calculation (LOW <= 5, MEDIUM 6-15, HIGH > 15, and configurable thresholds)
7. Unsupported / ambiguous request handling & unverified claims
8. Evidence grounding (file, symbol, lines, relationship)
9. Output formatting and JSON serialization
10. Agent tool plan_code_change integration & intent classification
11. REST API endpoints (POST and GET /api/changes/plan)
12. CLI command execution (run_plan_change)
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import create_plan_code_change_tool
from app.changes.models import ChangePlanEvidence, CodeChangePlan
from app.changes.planner import ChangeImpactPlanner
from app.changes.risk import calculate_plan_risk
from app.graph.builder import GraphBuilder
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import app, run_plan_change
from app.vector_store.qdrant_store import ValidationError


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_graph() -> GraphStore:
    """Builds a mock dependency graph for testing."""
    graph = GraphStore()

    # Target node: GraphBuilder.build
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

    # Direct caller 1: _resolve_graph
    caller1 = GraphNode(
        id="function:app/agent/tools.py:_resolve_graph",
        name="_resolve_graph",
        node_type=NodeType.FUNCTION,
        file_path="app/agent/tools.py",
        start_line=1540,
        end_line=1560,
    )
    graph.add_node(caller1)
    graph.add_edge(GraphEdge(
        source_id=caller1.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
        line_number=1545,
    ))

    # Direct caller 2: run_graph_build
    caller2 = GraphNode(
        id="function:app/main.py:run_graph_build",
        name="run_graph_build",
        node_type=NodeType.FUNCTION,
        file_path="app/main.py",
        start_line=1350,
        end_line=1375,
    )
    graph.add_node(caller2)
    graph.add_edge(GraphEdge(
        source_id=caller2.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
        line_number=1360,
    ))

    # Test caller: test_graph_builder_build
    test_caller = GraphNode(
        id="function:tests/test_graph_builder.py:test_graph_builder_build",
        name="test_graph_builder_build",
        node_type=NodeType.FUNCTION,
        file_path="tests/test_graph_builder.py",
        start_line=10,
        end_line=25,
    )
    graph.add_node(test_caller)
    graph.add_edge(GraphEdge(
        source_id=test_caller.id,
        target_id=target.id,
        edge_type=EdgeType.CALLS,
        line_number=15,
    ))

    # Indirect caller: main calling run_graph_build
    indirect = GraphNode(
        id="function:app/main.py:main",
        name="main",
        node_type=NodeType.FUNCTION,
        file_path="app/main.py",
        start_line=1880,
        end_line=2050,
    )
    graph.add_node(indirect)
    graph.add_edge(GraphEdge(
        source_id=indirect.id,
        target_id=caller2.id,
        edge_type=EdgeType.CALLS,
        line_number=1980,
    ))

    return graph


# ==============================================================================
# 1. Deterministic Risk Calculation Tests
# ==============================================================================

def test_risk_calculation_thresholds():
    assert calculate_plan_risk(0) == "LOW"
    assert calculate_plan_risk(5) == "LOW"
    assert calculate_plan_risk(6) == "MEDIUM"
    assert calculate_plan_risk(15) == "MEDIUM"
    assert calculate_plan_risk(16) == "HIGH"
    assert calculate_plan_risk(100) == "HIGH"


def test_custom_risk_calculation_thresholds():
    assert calculate_plan_risk(2, low_threshold=2, medium_threshold=5) == "LOW"
    assert calculate_plan_risk(3, low_threshold=2, medium_threshold=5) == "MEDIUM"
    assert calculate_plan_risk(6, low_threshold=2, medium_threshold=5) == "HIGH"


# ==============================================================================
# 2. Known Symbol Change Tests
# ==============================================================================

def test_plan_change_known_symbol(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Improve GraphBuilder.build performance", graph=sample_graph)

    assert plan.target_symbol == "GraphBuilder.build"
    assert plan.target_file == "app/graph/builder.py"
    assert "_resolve_graph" in plan.affected_symbols or "run_graph_build" in plan.affected_symbols
    assert "app/agent/tools.py" in plan.affected_files or "app/main.py" in plan.affected_files
    assert any("test_graph_builder" in t for t in plan.relevant_tests)
    assert plan.risk == "LOW"  # <= 5 affected symbols
    assert len(plan.evidence) >= 1
    assert any(e.relationship == "Target definition" for e in plan.evidence)
    assert any("caller" in e.relationship.lower() or "tests" in e.relationship.lower() for e in plan.evidence)
    assert len(plan.unverified) == 0


def test_plan_change_symbol_short_name(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Optimize build speed", graph=sample_graph)

    assert "build" in plan.target_symbol
    assert plan.target_file == "app/graph/builder.py"
    assert len(plan.evidence) > 0


# ==============================================================================
# 3. File-Based Change Tests
# ==============================================================================

def test_plan_change_file_based(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Refactor app/graph/builder.py", graph=sample_graph)

    assert plan.target_file == "app/graph/builder.py"
    assert "app/graph/builder.py" in plan.affected_files
    assert len(plan.relevant_tests) > 0
    assert len(plan.evidence) >= 1


# ==============================================================================
# 4. Direct & Indirect Impact and High Risk Simulation
# ==============================================================================

def test_plan_change_indirect_and_high_risk(project_root: Path):
    graph = GraphStore()
    target = GraphNode(
        id="function:app/core.py:core_fn",
        name="core_fn",
        node_type=NodeType.FUNCTION,
        file_path="app/core.py",
        start_line=1,
        end_line=50,
    )
    graph.add_node(target)

    # Add 20 dependent callers to trigger HIGH risk
    for i in range(20):
        caller = GraphNode(
            id=f"function:app/mod_{i}.py:caller_{i}",
            name=f"caller_{i}",
            node_type=NodeType.FUNCTION,
            file_path=f"app/mod_{i}.py",
            start_line=1,
            end_line=10,
        )
        graph.add_node(caller)
        graph.add_edge(GraphEdge(
            source_id=caller.id,
            target_id=target.id,
            edge_type=EdgeType.CALLS,
            line_number=5,
        ))

    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Refactor core_fn", graph=graph)

    assert len(plan.affected_symbols) >= 20
    assert plan.risk == "HIGH"
    assert "High blast radius" in plan.reason


# ==============================================================================
# 5. Unsupported / Ambiguous Request Handling
# ==============================================================================

def test_plan_change_unverified_target(project_root: Path):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Improve completely_invented_nonexistent_crypto_module_xyz", graph=GraphStore())

    assert len(plan.unverified) > 0
    assert "could not be verified" in plan.unverified[0]
    assert "Unverified:" in plan.to_formatted_string()


def test_plan_change_empty_request(project_root: Path):
    planner = ChangeImpactPlanner(project_root=project_root)
    with pytest.raises(ValidationError):
        planner.plan_change("")


# ==============================================================================
# 6. Output Formatting and Evidence Verification
# ==============================================================================

def test_code_change_plan_formatted_string():
    plan = CodeChangePlan(
        change_request="Improve GraphBuilder.build performance",
        target_symbol="GraphBuilder.build",
        target_file="app/graph/builder.py",
        target_lines="38-328",
        affected_files=["app/graph/builder.py", "app/agent/tools.py", "app/main.py"],
        affected_symbols=["_resolve_graph", "run_graph_build"],
        relevant_tests=["test_graph_builder.py", "test_graph_builder_build (tests/test_graph_builder.py:10)"],
        recommended_order=[
            "Implement core logic changes in GraphBuilder.build in app/graph/builder.py:38-328",
            "Update and verify direct dependents: _resolve_graph, run_graph_build",
            "Execute and update relevant tests: test_graph_builder.py",
        ],
        risk="LOW",
        reason="Target 'GraphBuilder.build' has 2 direct dependent(s) and 0 indirect dependent(s) across 3 file(s).",
        evidence=[
            ChangePlanEvidence(
                file="app/graph/builder.py",
                symbol="GraphBuilder.build",
                lines="38-328",
                relationship="Target definition",
            ),
            ChangePlanEvidence(
                file="app/agent/tools.py",
                symbol="_resolve_graph",
                lines="1540",
                relationship="Direct caller (calls)",
            ),
        ],
        unverified=[],
    )

    formatted = plan.to_formatted_string()
    assert "Change Request:\nImprove GraphBuilder.build performance" in formatted
    assert "Target:\nGraphBuilder.build" in formatted
    assert "Affected Files:\n- app/graph/builder.py" in formatted
    assert "Affected Symbols:\n- _resolve_graph" in formatted
    assert "Relevant Tests:\n- test_graph_builder.py" in formatted
    assert "Recommended Change Order:\n1. Implement core logic" in formatted
    assert "Risk:\nLOW" in formatted
    assert "Reason:\nTarget 'GraphBuilder.build'" in formatted
    assert "Evidence:\n- File: app/graph/builder.py" in formatted
    assert "Unverified:" not in formatted  # Unverified only shown when non-empty

    d = plan.to_dict()
    assert d["change_request"] == "Improve GraphBuilder.build performance"
    assert d["risk"] == "LOW"
    assert len(d["evidence"]) == 2


# ==============================================================================
# 7. Agent Tool and Intent Classification Tests
# ==============================================================================

def test_intent_classification_for_change_plan():
    intent1 = classify_question_intent("Plan changes for GraphBuilder.build")
    assert intent1.intent == QuestionIntent.CHANGE_PLAN

    intent2 = classify_question_intent("How should I refactor auth.py?")
    assert intent2.intent == QuestionIntent.CHANGE_PLAN

    intent3 = classify_question_intent("Improve GraphBuilder.build performance")
    assert intent3.intent == QuestionIntent.CHANGE_PLAN


def test_agent_plan_code_change_tool(project_root: Path, sample_graph: GraphStore):
    tool = create_plan_code_change_tool(graph=sample_graph, project_root=project_root)
    assert tool["name"] == "plan_code_change"
    res = tool["func"]("Improve GraphBuilder.build performance")
    assert "data" in res
    assert "formatted_text" in res
    assert "sources" in res
    assert res["data"]["target"] == "GraphBuilder.build"


# ==============================================================================
# 8. REST API Endpoints Tests
# ==============================================================================

def test_api_plan_change_post(client: TestClient):
    response = client.post(
        "/api/changes/plan",
        json={"change_request": "Improve GraphBuilder.build performance"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["change_request"] == "Improve GraphBuilder.build performance"
    assert "target" in data
    assert "affected_files" in data
    assert "affected_symbols" in data
    assert "relevant_tests" in data
    assert "recommended_order" in data
    assert "risk" in data
    assert "reason" in data
    assert "evidence" in data


def test_api_plan_change_get(client: TestClient):
    response = client.get(
        "/api/changes/plan",
        params={"change_request": "Refactor app/graph/builder.py"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "target" in data
    assert "risk" in data


def test_api_plan_change_empty(client: TestClient):
    response = client.post("/api/changes/plan", json={"change_request": ""})
    assert response.status_code in (400, 422)


# ==============================================================================
# 9. CLI Command Tests
# ==============================================================================

def test_cli_run_plan_change_text(capsys):
    run_plan_change(change_request="Improve GraphBuilder.build performance", as_json=False)
    captured = capsys.readouterr()
    assert "Change Request:" in captured.out
    assert "Target:" in captured.out
    assert "Affected Files:" in captured.out
    assert "Risk:" in captured.out
    assert "Reason:" in captured.out
    assert "Evidence:" in captured.out


def test_cli_run_plan_change_json(capsys):
    run_plan_change(change_request="Improve GraphBuilder.build performance", as_json=True)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["change_request"] == "Improve GraphBuilder.build performance"
    assert "risk" in parsed
    assert "evidence" in parsed
    assert "recommended_order" in parsed
