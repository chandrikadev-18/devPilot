"""
Tests for DevPilot v1.5 Agent + API Integration (POST /api/ask and POST /api/agent/ask).
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm import LLMAuthenticationError, LLMError
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall


@pytest.fixture
def client():
    return TestClient(app)


class MockTestLLM(LLMProvider):
    """Mock LLM Provider for unit testing agent endpoint interactions."""

    def __init__(self, responses=None):
        self._responses = list(responses or [
            LLMChatResponse(
                content="GraphBuilder.build coordinates AST extraction and dependency graph building.",
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
        return LLMChatResponse(content="Final synthesized response.")


# ============================================================================
# 1. POST /api/ask Success & Response Structure Tests
# ============================================================================

@patch("app.api.agent.create_llm_provider")
def test_api_ask_direct_answer(mock_create_llm, client):
    """Test POST /api/ask returns structured response without tool calls."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content="GraphBuilder.build constructs the graph by parsing Python files.",
            tool_calls=[],
        )
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "What is GraphBuilder.build?", "project_dir": "."}
    resp = client.post("/api/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == payload["question"]
    assert "GraphBuilder.build" in data["answer"]
    assert data["tools_used"] == []
    assert isinstance(data["sources"], list)
    assert "metadata" in data
    assert data["metadata"]["iterations"] >= 1
    assert data["metadata"]["stopped_reason"] == "completed"
    assert "tool_executions" in data["metadata"]
    assert data["metadata"]["tool_executions"] == []


@patch("app.api.agent.create_llm_provider")
def test_api_ask_with_graph_tools(mock_create_llm, client):
    """Test POST /api/ask with graph tool execution and tool metadata tracking."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="find_symbol", arguments={"symbol_name": "GraphBuilder.build"}),
            ],
        ),
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc2", name="get_dependencies", arguments={"symbol": "GraphBuilder.build", "depth": 2}),
            ],
        ),
        LLMChatResponse(
            content="GraphBuilder.build depends on extract_file, scan, and GraphStore.",
            tool_calls=[],
        ),
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "What does GraphBuilder.build depend on?", "project_dir": "."}
    resp = client.post("/api/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["question"] == payload["question"]
    assert "find_symbol" in data["tools_used"]
    assert "get_dependencies" in data["tools_used"]
    assert "extract_file" in data["answer"] or "depends on" in data["answer"]

    # Verify tool execution metadata
    tool_execs = data["metadata"]["tool_executions"]
    assert len(tool_execs) == 2
    assert tool_execs[0]["tool"] == "find_symbol"
    assert tool_execs[0]["status"] == "success"
    assert tool_execs[0]["duration_ms"] >= 0.0
    assert tool_execs[1]["tool"] == "get_dependencies"
    assert tool_execs[1]["status"] == "success"
    assert tool_execs[1]["duration_ms"] >= 0.0


@patch("app.api.agent.create_llm_provider")
def test_api_agent_ask_endpoint_parity(mock_create_llm, client):
    """Test POST /api/agent/ask works identically to /api/ask."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content="Impact analysis shows affected modules.",
            tool_calls=[],
        )
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "What is the impact of changing GraphBuilder?", "project_dir": "."}
    resp = client.post("/api/agent/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == payload["question"]
    assert "Impact analysis" in data["answer"]
    assert "metadata" in data


# ============================================================================
# 2. Validation & Error Handling Tests
# ============================================================================

def test_api_ask_empty_question(client):
    """Test POST /api/ask with empty string returns 400."""
    resp = client.post("/api/ask", json={"question": ""})
    assert resp.status_code in (400, 422)


def test_api_ask_whitespace_question(client):
    """Test POST /api/ask with whitespace-only question returns 400."""
    resp = client.post("/api/ask", json={"question": "   "})
    assert resp.status_code == 400
    assert "cannot be empty" in resp.json()["detail"].lower()


def test_api_ask_missing_payload(client):
    """Test POST /api/ask with missing question field returns 422."""
    resp = client.post("/api/ask", json={})
    assert resp.status_code == 422


def test_api_ask_invalid_project_dir(client):
    """Test POST /api/ask with non-existent project directory returns 400."""
    resp = client.post("/api/ask", json={"question": "Where is main?", "project_dir": "invalid_dir_999"})
    assert resp.status_code == 400
    assert "directory does not exist" in resp.json()["detail"].lower()


@patch("app.api.agent.create_llm_provider")
def test_api_ask_llm_auth_error(mock_create_llm, client):
    """Test POST /api/ask with missing LLM API key returns 401."""
    mock_create_llm.side_effect = LLMAuthenticationError("GROQ_API_KEY is not set")
    resp = client.post("/api/ask", json={"question": "Explain graph."})
    assert resp.status_code == 401
    assert "api key is not configured" in resp.json()["detail"].lower()


class ErrorLLM(LLMProvider):
    """Mock LLM Provider that raises LLMError."""

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages, tools=None):
        raise LLMError("Rate limit exceeded")


@patch("app.api.agent.create_llm_provider")
def test_api_ask_llm_upstream_error(mock_create_llm, client):
    """Test POST /api/ask with LLM provider failure returns 502."""
    mock_create_llm.side_effect = None
    mock_create_llm.return_value = ErrorLLM()

    resp = client.post("/api/ask", json={"question": "Explain graph."})
    assert resp.status_code == 502, f"Got status {resp.status_code}: {resp.text}"
    assert "llm error" in resp.json()["detail"].lower()


@patch("app.api.agent._get_vector_store")
def test_api_ask_vector_store_error(mock_get_store, client):
    """Test POST /api/ask returns 500 when vector store fails."""
    from app.vector_store.qdrant_store import VectorStoreError
    mock_get_store.side_effect = VectorStoreError("Disk I/O failure")

    resp = client.post("/api/ask", json={"question": "Where is main?"})
    assert resp.status_code == 500
    assert "vector store error" in resp.json()["detail"].lower()


# ============================================================================
# 3. Agent Execution & Graph Tools API Tests
# ============================================================================

@patch("app.api.agent.create_llm_provider")
def test_api_agent_execute_endpoint(mock_create_llm, client):
    """Test POST /api/agent/execute endpoint."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content="Execution result for test query.",
            tool_calls=[],
        )
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "Explain project structure", "project_dir": "."}
    resp = client.post("/api/agent/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == payload["question"]
    assert "Execution result" in data["answer"]


@patch("app.api.agent.create_llm_provider")
def test_api_ask_with_all_graph_tools(mock_create_llm, client):
    """Test POST /api/ask executing callers, callees, dependents, impact, and file_dependencies."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="get_callers", arguments={"symbol": "GraphBuilder.build"}),
                ToolCall(id="tc2", name="get_callees", arguments={"symbol": "GraphBuilder.build"}),
            ],
        ),
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc3", name="get_dependents", arguments={"symbol": "GraphBuilder.build", "depth": 1}),
                ToolCall(id="tc4", name="get_impact", arguments={"symbol": "GraphBuilder.build", "depth": 2}),
                ToolCall(id="tc5", name="get_file_dependencies", arguments={"file_path": "app/graph/builder.py"}),
            ],
        ),
        LLMChatResponse(
            content="GraphBuilder.build callers, callees, dependents, impact, and file dependencies analyzed.",
            tool_calls=[],
        ),
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "Analyze GraphBuilder.build relationships", "project_dir": "."}
    resp = client.post("/api/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    expected_tools = ["get_callers", "get_callees", "get_dependents", "get_impact", "get_file_dependencies"]
    for t in expected_tools:
        assert t in data["tools_used"]

    tool_execs = data["metadata"]["tool_executions"]
    assert len(tool_execs) == 5
    for exec_item in tool_execs:
        assert exec_item["status"] == "success"
        assert exec_item["duration_ms"] >= 0.0


@patch("app.api.agent.create_llm_provider")
def test_api_ask_symbol_not_found_handling(mock_create_llm, client):
    """Test POST /api/ask when a symbol is not found, agent returns graceful response without crashing."""
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="find_symbol", arguments={"symbol_name": "NonExistentClass999"}),
            ],
        ),
        LLMChatResponse(
            content="Symbol not found:\nNonExistentClass999\n\nSuggestions:\n- Check the symbol name",
            tool_calls=[],
        ),
    ])
    mock_create_llm.return_value = mock_llm

    payload = {"question": "Explain NonExistentClass999", "project_dir": "."}
    resp = client.post("/api/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "find_symbol" in data["tools_used"]
    assert "Symbol not found" in data["answer"]


@patch("app.api.agent.create_llm_provider")
def test_api_ask_response_schema_conformance(mock_create_llm, client):
    """Test POST /api/ask response strictly conforms to AgentAskResponse schema."""
    from app.schemas.agent import AgentAskResponse
    mock_llm = MockTestLLM([
        LLMChatResponse(
            content="Standard structured response.",
            tool_calls=[],
        )
    ])
    mock_create_llm.return_value = mock_llm

    resp = client.post("/api/ask", json={"question": "What is DevPilot?"})
    assert resp.status_code == 200
    validated = AgentAskResponse(**resp.json())
    assert validated.question == "What is DevPilot?"
    assert validated.answer == "Standard structured response."
    assert isinstance(validated.tools_used, list)
    assert isinstance(validated.sources, list)
    assert isinstance(validated.metadata, dict)
    assert isinstance(validated.timing, dict)


# ============================================================================
# 4. CLI Compatibility Tests
# ============================================================================

def test_cli_ask_and_agent_commands_intact():
    """Verify CLI agent and ask entry points remain functional and callable."""
    from app.main import run_agent, run_ask
    assert callable(run_agent)
    assert callable(run_ask)





