"""
Tests for DevPilot v1.4 FastAPI REST API Layer.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall


@pytest.fixture
def client():
    return TestClient(app)


class MockAPILLM(LLMProvider):
    """Mock LLM Provider for testing agent endpoints without external API calls."""

    def __init__(self, responses=None):
        self._responses = list(responses or [
            LLMChatResponse(
                content="GraphBuilder.build is used by run_graph_build to construct the dependency graph.",
                tool_calls=[],
            )
        ])
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages, tools=None):
        self.call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return LLMChatResponse(content="Final synthesized answer.")


# ============================================================================
# 1. Health Endpoint Tests
# ============================================================================

def test_api_health(client):
    """Test GET /api/health returns correct status, service, and version."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "DevPilot"
    assert data["version"] == "1.4"


# ============================================================================
# 2. Graph Endpoints Tests
# ============================================================================

def test_graph_info(client):
    """Test GET /api/graph/info returns complete node and edge statistics."""
    resp = client.get("/api/graph/info", params={"project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_nodes" in data
    assert "total_edges" in data
    assert "files" in data
    assert "classes" in data
    assert "functions" in data
    assert "methods" in data
    assert "calls" in data
    assert data["total_nodes"] > 0
    assert data["total_edges"] > 0


def test_graph_callers(client):
    """Test GET /api/graph/callers returns callers for a known symbol."""
    resp = client.get("/api/graph/callers", params={"symbol": "GraphBuilder.build", "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert "total_callers" in data
    assert isinstance(data["callers"], list)


def test_graph_callees(client):
    """Test GET /api/graph/callees returns callees for a known symbol."""
    resp = client.get("/api/graph/callees", params={"symbol": "GraphBuilder.build", "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert "total_callees" in data
    assert isinstance(data["callees"], list)


def test_graph_dependencies(client):
    """Test GET /api/graph/dependencies returns downstream call dependencies."""
    resp = client.get("/api/graph/dependencies", params={"symbol": "GraphBuilder.build", "depth": 2, "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["depth"] == 2
    assert "total_dependencies" in data
    assert isinstance(data["dependencies"], list)


def test_graph_dependents(client):
    """Test GET /api/graph/dependents returns upstream callers."""
    resp = client.get("/api/graph/dependents", params={"symbol": "GraphBuilder.build", "depth": 2, "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["depth"] == 2
    assert "total_dependents" in data
    assert isinstance(data["dependents"], list)


def test_graph_impact(client):
    """Test GET /api/graph/impact returns complete static impact analysis."""
    resp = client.get("/api/graph/impact", params={"symbol": "GraphBuilder.build", "depth": 2, "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["depth"] == 2
    assert "analysis_type" in data
    assert "total_impacted" in data
    assert "direct_callers" in data
    assert "indirect_callers" in data
    assert "impacted_files" in data
    assert isinstance(data["impacted_files"], list)


# ============================================================================
# 3. Symbol Search Endpoint Tests
# ============================================================================

def test_search_symbol_found(client):
    """Test GET /api/search/symbol returns matches for existing symbol."""
    resp = client.get("/api/search/symbol", params={"query": "GraphBuilder.build", "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "GraphBuilder.build"
    assert data["total_matches"] >= 1
    assert len(data["matches"]) >= 1
    first_match = data["matches"][0]
    assert first_match["symbol_name"] == "build" or first_match["symbol_name"] == "GraphBuilder.build"
    assert "app/graph/builder.py" in first_match["file_path"].replace("\\", "/")


def test_search_symbol_not_found_default(client):
    """Test GET /api/search/symbol returns empty list when symbol is not found (strict=false)."""
    resp = client.get("/api/search/symbol", params={"query": "NonExistentSymbol999XYZ", "project_dir": "."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "NonExistentSymbol999XYZ"
    assert data["total_matches"] == 0
    assert data["matches"] == []


def test_search_symbol_not_found_strict(client):
    """Test GET /api/search/symbol returns 404 when strict=true and symbol is not found."""
    resp = client.get("/api/search/symbol", params={"query": "NonExistentSymbol999XYZ", "strict": "true", "project_dir": "."})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# 4. Agent Endpoint Tests
# ============================================================================

@patch("app.api.agent.create_llm_provider")
def test_agent_ask_success(mock_create_llm, client):
    """Test POST /api/agent/ask returns agent answer and tools used."""
    mock_llm = MockAPILLM([
        LLMChatResponse(
            content="GraphBuilder.build constructs the graph by parsing AST elements.",
            tool_calls=[],
        )
    ])
    mock_create_llm.return_value = mock_llm

    payload = {
        "question": "What does GraphBuilder.build do?",
        "project_dir": ".",
    }
    resp = client.post("/api/agent/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == payload["question"]
    assert "GraphBuilder.build" in data["answer"]
    assert isinstance(data["tools_used"], list)


@patch("app.api.agent.create_llm_provider")
def test_agent_ask_with_tools(mock_create_llm, client):
    """Test POST /api/agent/ask returns recorded tool calls in tools_used."""
    mock_llm = MockAPILLM([
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="find_symbol", arguments={"symbol_name": "GraphBuilder.build"})
            ],
        ),
        LLMChatResponse(
            content="Found GraphBuilder.build in app/graph/builder.py.",
            tool_calls=[],
        ),
    ])
    mock_create_llm.return_value = mock_llm

    payload = {
        "question": "Where is GraphBuilder.build defined?",
        "project_dir": ".",
    }
    resp = client.post("/api/agent/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "find_symbol" in data["tools_used"]
    assert "app/graph/builder.py" in data["answer"]


# ============================================================================
# 5. Validation & Error Handling Tests
# ============================================================================

def test_invalid_depth_zero(client):
    """Test graph endpoints with depth <= 0 return 400 Bad Request."""
    resp = client.get("/api/graph/dependencies", params={"symbol": "GraphBuilder.build", "depth": 0})
    assert resp.status_code == 400
    assert "depth" in resp.json()["detail"].lower()


def test_invalid_depth_large(client):
    """Test graph endpoints with depth > 10 return 400 Bad Request."""
    resp = client.get("/api/graph/impact", params={"symbol": "GraphBuilder.build", "depth": 99})
    assert resp.status_code == 400
    assert "depth" in resp.json()["detail"].lower()


def test_empty_symbol_error(client):
    """Test empty symbol parameter returns 400 Bad Request."""
    resp = client.get("/api/graph/callers", params={"symbol": "   "})
    assert resp.status_code == 400
    assert "symbol" in resp.json()["detail"].lower()


def test_missing_required_parameter(client):
    """Test missing required parameter returns 422 Unprocessable Entity."""
    resp = client.get("/api/graph/callers")
    assert resp.status_code == 422


def test_agent_empty_question(client):
    """Test POST /api/agent/ask with empty question returns 422 / 400."""
    resp = client.post("/api/agent/ask", json={"question": ""})
    assert resp.status_code in (400, 422)


def test_nonexistent_project_dir(client):
    """Test invalid project directory returns 400 Bad Request."""
    resp = client.get("/api/graph/info", params={"project_dir": "non_existent_folder_xyz_123"})
    assert resp.status_code == 400
    assert "directory does not exist" in resp.json()["detail"].lower()


# ============================================================================
# 6. CORS & Swagger / OpenAPI Tests
# ============================================================================

def test_cors_headers(client):
    """Test CORS headers are returned for allowed origins."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    }
    resp = client.options("/api/health", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_openapi_schema(client):
    """Test /openapi.json schema endpoint returns valid OpenAPI spec."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "DevPilot API"
    assert schema["info"]["version"] == "1.4"
    assert "/api/health" in schema["paths"]
    assert "/api/graph/info" in schema["paths"]
    assert "/api/graph/callers" in schema["paths"]
    assert "/api/graph/impact" in schema["paths"]
    assert "/api/search/symbol" in schema["paths"]
    assert "/api/agent/ask" in schema["paths"]


def test_swagger_docs(client):
    """Test /docs Swagger UI endpoint returns 200 OK."""
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower() or "html" in resp.text.lower()
