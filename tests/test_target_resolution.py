"""
Tests for DevPilot v1.9.1 Target Resolution & Symbol Disambiguation.

Covers:
1. Exact qualified symbol resolution (GraphBuilder.build, AuthService.verify_password, GraphStore.add_edge)
2. Priority over semantic search (exact qualified symbols must NOT be overridden by semantic search)
3. Exact symbol with file/class context (app/graph/builder.py:build, build in builder.py)
4. Exact unqualified symbol resolution (unique symbols vs ambiguous symbols)
5. Semantic search fallback for natural language requests (Where is authentication handled?)
6. Ambiguity detection and structured ambiguity handling
7. Regression tests for specific prompt patterns:
   - "Explain what would be affected if GraphBuilder.build changes"
   - "What does GraphBuilder.build depend on?"
   - "Where is authentication handled?"
   - "Explain the impact of AuthService.verify_password"
8. CLI and AutonomousFixService integration
"""

import json
from pathlib import Path
import pytest

from app.agent.intent import QuestionIntent, classify_question_intent
from app.changes.autonomous_fix import AutonomousFixService
from app.changes.models import FixMode
from app.changes.planner import ChangeImpactPlanner
from app.changes.target_resolver import ResolvedTarget, TargetResolver
from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.store import GraphStore
from app.main import run_fix


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def sample_graph() -> GraphStore:
    """Builds a sample graph with known symbols."""
    graph = GraphStore()

    # GraphBuilder.build
    builder_node = GraphNode(
        id="method:app/graph/builder.py:GraphBuilder.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/graph/builder.py",
        start_line=38,
        end_line=328,
        metadata={"parent_class": "GraphBuilder"},
    )
    graph.add_node(builder_node)

    # AuthService.verify_password
    auth_node = GraphNode(
        id="method:sample_project/auth.py:AuthService.verify_password",
        name="verify_password",
        node_type=NodeType.METHOD,
        file_path="sample_project/auth.py",
        start_line=11,
        end_line=12,
        metadata={"parent_class": "AuthService"},
    )
    graph.add_node(auth_node)

    # GraphStore.add_edge
    store_node = GraphNode(
        id="method:app/graph/store.py:GraphStore.add_edge",
        name="add_edge",
        node_type=NodeType.METHOD,
        file_path="app/graph/store.py",
        start_line=50,
        end_line=65,
        metadata={"parent_class": "GraphStore"},
    )
    graph.add_node(store_node)

    # Caller of GraphBuilder.build
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
        target_id=builder_node.id,
        edge_type=EdgeType.CALLS,
        line_number=1545,
    ))

    return graph


# ==============================================================================
# 1. Intent Classification Regression Tests
# ==============================================================================

def test_intent_classification_regressions():
    # 1. Explain what would be affected if GraphBuilder.build changes
    q1 = classify_question_intent("Explain what would be affected if GraphBuilder.build changes")
    assert q1.intent == QuestionIntent.IMPACT
    assert q1.target_symbol == "GraphBuilder.build"

    # 2. What does GraphBuilder.build depend on?
    q2 = classify_question_intent("What does GraphBuilder.build depend on?")
    assert q2.intent == QuestionIntent.DEPENDENCIES
    assert q2.target_symbol == "GraphBuilder.build"

    # 3. Where is authentication handled?
    q3 = classify_question_intent("Where is authentication handled?")
    assert q3.intent == QuestionIntent.SEMANTIC_SEARCH
    assert "authentication" in q3.target_symbol.lower()

    # 4. Explain the impact of AuthService.verify_password
    q4 = classify_question_intent("Explain the impact of AuthService.verify_password")
    assert q4.intent == QuestionIntent.IMPACT
    assert q4.target_symbol == "AuthService.verify_password"


# ==============================================================================
# 2. TargetResolver Unit Tests
# ==============================================================================

def test_target_resolver_exact_qualified(project_root: Path, sample_graph: GraphStore):
    resolver = TargetResolver(project_root=project_root)

    # GraphBuilder.build
    res1 = resolver.resolve("Explain what would be affected if GraphBuilder.build changes", graph=sample_graph)
    assert res1.target_symbol == "GraphBuilder.build"
    assert res1.target_file == "app/graph/builder.py"
    assert res1.resolution_method == "exact_qualified"
    assert res1.confidence == 1.0
    assert not res1.is_ambiguous

    # AuthService.verify_password
    res2 = resolver.resolve("Explain the impact of AuthService.verify_password", graph=sample_graph)
    assert res2.target_symbol == "AuthService.verify_password"
    assert res2.target_file == "sample_project/auth.py"
    assert res2.resolution_method == "exact_qualified"
    assert res2.confidence == 1.0

    # GraphStore.add_edge
    res3 = resolver.resolve("What breaks if GraphStore.add_edge changes?", graph=sample_graph)
    assert res3.target_symbol == "GraphStore.add_edge"
    assert res3.target_file == "app/graph/store.py"
    assert res3.resolution_method == "exact_qualified"
    assert res3.confidence == 1.0


def test_target_resolver_qualified_not_overridden_by_semantic_search(project_root: Path, sample_graph: GraphStore):
    """Ensures semantic search never overrides an exact qualified symbol."""
    resolver = TargetResolver(project_root=project_root)
    res = resolver.resolve("Explain what would be affected if GraphBuilder.build changes", graph=sample_graph)

    assert res.target_symbol == "GraphBuilder.build"
    assert res.target_file == "app/graph/builder.py"
    assert res.target_symbol != "build_chunk_payload"
    assert res.target_file != "app/vector_store/qdrant_store.py"
    assert res.resolution_method == "exact_qualified"


def test_target_resolver_symbol_with_file_context(project_root: Path, sample_graph: GraphStore):
    resolver = TargetResolver(project_root=project_root)

    # Symbol with explicit file path
    res = resolver.resolve("Modify build in app/graph/builder.py", graph=sample_graph)
    assert res.target_file == "app/graph/builder.py"
    assert "build" in res.target_symbol
    assert res.resolution_method == "symbol_with_context"
    assert res.confidence >= 0.95


def test_target_resolver_unqualified_ambiguous(project_root: Path):
    """When a short symbol name like 'build' matches multiple distinct files, it must be flagged as ambiguous."""
    graph = GraphStore()
    graph.add_node(GraphNode(
        id="method:app/graph/builder.py:GraphBuilder.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/graph/builder.py",
        start_line=38,
        end_line=328,
        metadata={"parent_class": "GraphBuilder"},
    ))
    graph.add_node(GraphNode(
        id="method:app/rag/context_builder.py:ContextBuilder.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/rag/context_builder.py",
        start_line=20,
        end_line=60,
        metadata={"parent_class": "ContextBuilder"},
    ))

    resolver = TargetResolver(project_root=project_root)
    res = resolver.resolve("Refactor build", graph=graph)

    assert res.is_ambiguous is True
    assert res.resolution_method == "ambiguous"
    assert res.confidence == 0.0
    assert len(res.ambiguity_candidates) == 2


# ==============================================================================
# 3. ChangeImpactPlanner Integration Regression Tests
# ==============================================================================

def test_planner_regression_graph_builder_build(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Explain what would be affected if GraphBuilder.build changes", graph=sample_graph)

    assert plan.target == "GraphBuilder.build"
    assert plan.target_symbol == "GraphBuilder.build"
    assert plan.target_file == "app/graph/builder.py"
    assert plan.target_lines is not None
    assert plan.resolution_method == "exact_qualified"
    assert plan.confidence == 1.0
    assert "_resolve_graph" in plan.affected_symbols
    assert plan.target_symbol != "build_chunk_payload"

    # Verify JSON serialization contains required fields
    plan_dict = plan.to_dict()
    assert plan_dict["target"] == "GraphBuilder.build"
    assert plan_dict["target_symbol"] == "GraphBuilder.build"
    assert plan_dict["target_file"] == "app/graph/builder.py"
    assert plan_dict["target_lines"] is not None
    assert plan_dict["resolution_method"] == "exact_qualified"
    assert plan_dict["confidence"] == 1.0


def test_planner_regression_graph_builder_dependencies(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("What does GraphBuilder.build depend on?", graph=sample_graph)

    assert plan.target == "GraphBuilder.build"
    assert plan.target_symbol == "GraphBuilder.build"
    assert plan.target_file == "app/graph/builder.py"
    assert plan.resolution_method == "exact_qualified"
    assert plan.confidence == 1.0


def test_planner_regression_auth_service_impact(project_root: Path, sample_graph: GraphStore):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Explain the impact of AuthService.verify_password", graph=sample_graph)

    assert plan.target == "AuthService.verify_password"
    assert plan.target_symbol == "AuthService.verify_password"
    assert plan.target_file == "sample_project/auth.py"
    assert plan.resolution_method == "exact_qualified"
    assert plan.confidence == 1.0


def test_planner_regression_where_is_authentication_handled(project_root: Path):
    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Where is authentication handled?")

    # Natural language question -> falls back to semantic search or handles cleanly
    assert plan.resolution_method in ("semantic_search", "unresolved")
    assert plan.target != "build_chunk_payload"


def test_planner_ambiguous_target_generates_safe_plan(project_root: Path):
    graph = GraphStore()
    graph.add_node(GraphNode(
        id="method:app/a.py:A.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/a.py",
        start_line=1,
        end_line=10,
    ))
    graph.add_node(GraphNode(
        id="method:app/b.py:B.build",
        name="build",
        node_type=NodeType.METHOD,
        file_path="app/b.py",
        start_line=1,
        end_line=10,
    ))

    planner = ChangeImpactPlanner(project_root=project_root)
    plan = planner.plan_change("Refactor build", graph=graph)

    assert plan.resolution_method == "ambiguous"
    assert plan.confidence == 0.0
    assert plan.target_file == ""
    assert len(plan.unverified) > 0
    assert "ambiguous" in plan.unverified[0].lower()
    assert "Disambiguate" in plan.recommended_order[0]


# ==============================================================================
# 4. AutonomousFixService & CLI Acceptance Tests
# ==============================================================================

def test_autonomous_fix_service_plan_mode_regression(project_root: Path, sample_graph: GraphStore):
    service = AutonomousFixService(project_root=project_root)
    result = service.execute(
        request="Explain what would be affected if GraphBuilder.build changes",
        mode=FixMode.PLAN,
        graph=sample_graph,
    )

    assert result.status == "plan_only"
    assert result.plan is not None
    assert result.plan.target == "GraphBuilder.build"
    assert result.plan.target_symbol == "GraphBuilder.build"
    assert result.plan.target_file == "app/graph/builder.py"
    assert result.plan.resolution_method == "exact_qualified"
    assert result.plan.confidence == 1.0


def test_cli_fix_command_plan_json(project_root: Path, capsys):
    """End-to-end CLI execution test matching acceptance requirement."""
    run_fix(
        request="Explain what would be affected if GraphBuilder.build changes",
        mode="plan",
        project_dir=str(project_root),
        as_json=True,
    )
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["mode"] == "PLAN"
    assert data["status"] == "plan_only"
    plan_data = data["plan"]
    assert plan_data is not None
    assert plan_data["target"] == "GraphBuilder.build"
    assert plan_data["target_symbol"] == "GraphBuilder.build"
    assert plan_data["target_file"] == "app/graph/builder.py"
    assert plan_data["target_symbol"] != "build_chunk_payload"
    assert plan_data["resolution_method"] == "exact_qualified"
    assert plan_data["confidence"] == 1.0
