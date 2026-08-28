"""
Tests for DevPilot v1.8 Semantic Code Intelligence & Hybrid Search.

Covers:
- SemanticSymbolResult and SemanticSearchOutput models
- HybridCodeSearchEngine retrieval, ranking, and fallback logic
- Dependency Graph relationship expansion for search results
- Agent semantic_code_search tool
- Natural language intent classification for semantic queries
- REST API endpoints (POST /api/search/semantic, GET /api/search/semantic)
- CLI semantic-search command execution
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import create_semantic_code_search_tool
from app.main import app, run_semantic_search
from app.search.hybrid_search import HybridCodeSearchEngine
from app.search.models import SemanticSearchOutput, SemanticSymbolResult
from app.vector_store.qdrant_store import ValidationError


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Model & Data Structure Tests
# ==============================================================================

def test_semantic_symbol_result_model():
    res = SemanticSymbolResult(
        symbol="authenticate_user",
        file="app/auth/service.py",
        start_line=42,
        end_line=71,
        score=0.89,
        reason="Handles user credential verification",
        symbol_type="function",
        related_symbols=["verify_password", "create_access_token"],
    )
    data = res.to_dict()
    assert data["symbol"] == "authenticate_user"
    assert data["file"] == "app/auth/service.py"
    assert data["start_line"] == 42
    assert data["score"] == 0.89
    assert "verify_password" in data["related_symbols"]


def test_semantic_search_output_formatting():
    output = SemanticSearchOutput(
        query="Where is authentication handled?",
        results=[
            SemanticSymbolResult(
                symbol="authenticate_user",
                file="app/auth/service.py",
                start_line=42,
                end_line=71,
                score=0.89,
                reason="Handles user credential verification",
                symbol_type="function",
                related_symbols=["verify_password", "create_access_token"],
            )
        ],
    )
    text = output.to_formatted_text()
    assert "Semantic Search Results for: 'Where is authentication handled?'" in text
    assert "authenticate_user()" in text
    assert "app/auth/service.py:42-71" in text
    assert "Score:    0.89" in text
    assert "Related:  verify_password, create_access_token" in text


# ==============================================================================
# 2. Hybrid Code Search Engine Tests
# ==============================================================================

def test_hybrid_search_graph_query(project_root: Path):
    engine = HybridCodeSearchEngine(project_root=project_root)
    output = engine.search("build dependency graph", top_k=3)
    assert output.query == "build dependency graph"
    assert len(output.results) > 0
    # Should find GraphBuilder.build or similar graph builders
    found_symbols = [r.symbol for r in output.results]
    assert any("build" in s.lower() or "graph" in s.lower() for s in found_symbols)
    # Check score bounds
    for r in output.results:
        assert 0.0 <= r.score <= 1.0


def test_hybrid_search_empty_query(project_root: Path):
    engine = HybridCodeSearchEngine(project_root=project_root)
    with pytest.raises(ValidationError):
        engine.search("")


def test_hybrid_search_invalid_top_k(project_root: Path):
    engine = HybridCodeSearchEngine(project_root=project_root)
    with pytest.raises(ValidationError):
        engine.search("graph", top_k=-1)


def test_hybrid_search_ast_fallback(project_root: Path):
    engine = HybridCodeSearchEngine(project_root=project_root)
    candidates = engine._fallback_ast_scan("git intelligence blame", top_k=5)
    assert isinstance(candidates, list)
    assert len(candidates) > 0
    symbols = [c["symbol"] for c in candidates]
    assert any("git" in s.lower() or "blame" in s.lower() for s in symbols)


# ==============================================================================
# 3. Agent Semantic Code Search Tool Tests
# ==============================================================================

def test_semantic_code_search_tool(project_root: Path):
    tool_spec = create_semantic_code_search_tool(project_root=project_root)
    assert tool_spec["name"] == "semantic_code_search"
    res = tool_spec["func"](query="building dependency graph", top_k=3)
    assert "data" in res
    assert "formatted_text" in res
    assert "sources" in res
    assert isinstance(res["sources"], list)
    assert len(res["sources"]) > 0


def test_semantic_code_search_tool_empty_query(project_root: Path):
    tool_spec = create_semantic_code_search_tool(project_root=project_root)
    res = tool_spec["func"](query="")
    assert "Search query cannot be empty" in res["data"]


# ==============================================================================
# 4. Intent Classification for Semantic Queries Tests
# ==============================================================================

def test_classify_intent_semantic_search():
    queries = [
        "Where is authentication handled?",
        "Find code related to database connections",
        "Where are JWT tokens validated?",
        "Which code is responsible for building the dependency graph?",
        "Find the implementation responsible for crawling websites",
        "Where do we handle API errors?",
        "Show me code related to password reset",
        "Which code handles API authentication?",
        "Where is functionality for caching implemented?",
    ]
    for q in queries:
        c = classify_question_intent(q)
        assert c.intent == QuestionIntent.SEMANTIC_SEARCH, f"Failed for query: {q}"
        assert "semantic_code_search" in c.preferred_tools


# ==============================================================================
# 5. REST API Endpoints Tests
# ==============================================================================

def test_api_semantic_search_post(client: TestClient):
    response = client.post(
        "/api/search/semantic",
        json={"query": "dependency graph construction", "top_k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "dependency graph construction"
    assert data["total_results"] > 0
    assert len(data["results"]) > 0
    first = data["results"][0]
    assert "symbol" in first
    assert "file" in first
    assert "score" in first
    assert 0.0 <= first["score"] <= 1.0


def test_api_semantic_search_get(client: TestClient):
    response = client.get(
        "/api/search/semantic",
        params={"query": "git commit blame history", "top_k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "git commit blame history"
    assert len(data["results"]) > 0


def test_api_semantic_search_empty_query(client: TestClient):
    response = client.get("/api/search/semantic", params={"query": ""})
    assert response.status_code == 422 or response.status_code == 400


# ==============================================================================
# 6. CLI Command Execution Tests
# ==============================================================================

def test_cli_semantic_search(capsys):
    run_semantic_search(query="dependency graph builder", top_k=3, as_json=True)
    captured = capsys.readouterr()
    assert "dependency graph builder" in captured.out
    assert "results" in captured.out
