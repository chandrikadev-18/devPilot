"""
Tests for Codebase Agent Orchestration and Multi-Tool Reasoning.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.agent import CodebaseAgent
from app.agent.state import AgentResult, AgentState
from app.agent.tool_registry import Tool, ToolRegistry
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall
from app.search.semantic_search import SearchResult, SemanticSearcher


class MockAgentLLM(LLMProvider):
    """Mock LLM Provider that yields a configured sequence of LLMChatResponses."""

    def __init__(self, responses: list[LLMChatResponse], provider_name: str = "groq", model_name: str = "mock-model"):
        self._responses = list(responses)
        self._provider_name = provider_name
        self._model_name = model_name
        self.call_count = 0
        self.recorded_messages = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def chat(self, messages, tools=None):
        self.call_count += 1
        self.recorded_messages.append(messages)
        if self._responses:
            return self._responses.pop(0)
        return LLMChatResponse(content="Fallback answer based on collected evidence.")


@pytest.fixture
def mock_tools():
    registry = ToolRegistry()

    def search_func(query: str, top_k: int = 5):
        return {
            "data": [{"file": "backend/auth.py", "symbol": "authenticate_user"}],
            "sources": [{
                "file_path": "backend/auth.py",
                "symbol_name": "authenticate_user",
                "symbol_type": "function",
                "start_line": 10,
                "end_line": 22,
                "score": 0.89,
            }],
        }

    def read_func(file_path: str):
        return {
            "data": {"file_path": file_path, "content": "def authenticate_user(): pass"},
            "sources": [{
                "file_path": file_path,
                "symbol_name": "file",
                "symbol_type": "file",
                "start_line": 1,
                "end_line": 20,
            }],
        }

    registry.register(Tool(
        name="search_code",
        description="Search code",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        func=search_func,
    ))
    registry.register(Tool(
        name="read_file",
        description="Read file",
        parameters={"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
        func=read_func,
    ))
    return registry


def test_agent_single_tool_call(mock_tools):
    """Verifies agent executes a tool call and generates final answer."""
    responses = [
        LLMChatResponse(
            tool_calls=[ToolCall(id="call_1", name="search_code", arguments={"query": "authentication"})]
        ),
        LLMChatResponse(content="Authentication is handled in backend/auth.py via authenticate_user()."),
    ]
    mock_llm = MockAgentLLM(responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=mock_tools, max_iterations=5)

    result = agent.run("Where is authentication handled?")

    assert result.question == "Where is authentication handled?"
    assert "Authentication is handled in backend/auth.py" in result.answer
    assert result.iterations == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool"] == "search_code"
    assert len(result.sources) == 1
    assert result.sources[0]["file_path"] == "backend/auth.py"
    assert result.stopped_reason == "completed"


def test_agent_multi_tool_reasoning(mock_tools):
    """Verifies multi-step tool calls (search_code then read_file)."""
    responses = [
        LLMChatResponse(
            tool_calls=[ToolCall(id="call_1", name="search_code", arguments={"query": "auth"})]
        ),
        LLMChatResponse(
            tool_calls=[ToolCall(id="call_2", name="read_file", arguments={"file_path": "backend/auth.py"})]
        ),
        LLMChatResponse(content="After inspecting backend/auth.py, authentication validates credentials."),
    ]
    mock_llm = MockAgentLLM(responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=mock_tools, max_iterations=5)

    result = agent.run("Explain the complete auth flow.")

    assert len(result.tool_calls) == 2
    assert result.tool_calls[0]["tool"] == "search_code"
    assert result.tool_calls[1]["tool"] == "read_file"
    assert len(result.sources) == 2
    assert result.stopped_reason == "completed"


def test_agent_max_iterations_limit(mock_tools):
    """Verifies agent halts and synthesizes answer when hitting max_iterations limit."""
    # LLM that always requests tools
    infinite_tool_responses = [
        LLMChatResponse(tool_calls=[ToolCall(id=f"call_{i}", name="search_code", arguments={"query": f"test_{i}"})])
        for i in range(10)
    ]
    mock_llm = MockAgentLLM(infinite_tool_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=mock_tools, max_iterations=2)

    result = agent.run("Perform exhaustive search.")

    assert result.iterations == 2
    assert result.stopped_reason == "max_iterations_reached"
    assert result.answer != ""


def test_agent_max_tool_calls_limit(mock_tools):
    """Verifies agent halts when exceeding max_tool_calls limit."""
    responses = [
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="search_code", arguments={"query": "q1"}),
                ToolCall(id="c2", name="search_code", arguments={"query": "q2"}),
                ToolCall(id="c3", name="search_code", arguments={"query": "q3"}),
            ]
        ),
    ]
    mock_llm = MockAgentLLM(responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=mock_tools, max_iterations=5, max_tool_calls=2)

    result = agent.run("Search many things.")
    assert len(result.tool_calls) == 2
    assert result.stopped_reason == "max_tool_calls_reached"


def test_agent_result_to_dict():
    """Verifies AgentResult JSON serialization."""
    res = AgentResult(
        question="Where is login?",
        answer="Login is in auth.py.",
        sources=[{"file_path": "auth.py", "symbol_name": "login"}],
        tool_calls=[{"tool": "search_code", "arguments": {"query": "login"}}],
        iterations=2,
        provider="groq",
        model="llama-3.3-70b-versatile",
        timing={"total": 1.25},
        stopped_reason="completed",
    )
    d = res.to_dict()
    assert d["question"] == "Where is login?"
    assert d["stopped_reason"] == "completed"
    assert json.loads(json.dumps(d)) == d


def test_agent_integration_with_sample_project(tmp_path):
    """End-to-end integration test with sample project and tool registry."""
    from app.agent import create_codebase_agent
    from app.search.semantic_search import SemanticSearcher

    mock_searcher = MagicMock(spec=SemanticSearcher)
    mock_searcher.search.return_value = [
        SearchResult(
            chunk_id="chunk-auth-1",
            score=0.91,
            file_path="sample_project/auth.py",
            symbol_name="AuthService",
            symbol_type="class",
            parent_symbol=None,
            start_line=4,
            end_line=12,
            code="class AuthService:\n    def hash_password(self, password): pass",
        )
    ]

    responses = [
        LLMChatResponse(
            tool_calls=[ToolCall(id="call_1", name="search_code", arguments={"query": "AuthService password hashing"})]
        ),
        LLMChatResponse(
            content="AuthService in sample_project/auth.py implements password hashing."
        ),
    ]
    mock_llm = MockAgentLLM(responses)

    agent = create_codebase_agent(
        llm=mock_llm,
        searcher=mock_searcher,
        project_root=Path("sample_project"),
    )

    result = agent.run("Where is AuthService password hashing implemented?")

    assert "AuthService in sample_project/auth.py" in result.answer
    assert len(result.sources) >= 1
    assert result.sources[0]["file_path"] == "sample_project/auth.py"
