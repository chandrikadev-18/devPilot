"""
Unit and integration tests for DevPilot Git tools and AI Agent integration.
"""

from pathlib import Path
import json
import pytest
import git

from app.agent.agent import CodebaseAgent
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools import (
    create_get_commit_tool,
    create_get_file_blame_tool,
    create_get_file_history_tool,
    create_get_last_commit_tool,
    create_get_recent_commits_tool,
)
from app.llm.base import (
    LLMChatResponse,
    LLMProvider,
    ToolCall,
)


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider that executes predefined script of responses / tool calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0
        self.received_messages = []

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages, tools=None):
        self.received_messages.append(messages)
        if self.call_count < len(self._responses):
            resp = self._responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMChatResponse(
            content="No more mock responses configured.",
            tool_calls=[],
            finish_reason="stop",
        )


@pytest.fixture
def test_git_project(tmp_path: Path) -> Path:
    """Creates a temporary initialized repository with commits for tool testing."""
    proj_dir = tmp_path / "agent_git_repo"
    proj_dir.mkdir()
    r = git.Repo.init(proj_dir)

    with r.config_writer() as config:
        config.set_value("user", "name", "Alice Dev")
        config.set_value("user", "email", "alice@example.com")

    f1 = proj_dir / "auth.py"
    f1.write_text("def authenticate_user(token):\n    return token == 'valid'\n", encoding="utf-8")
    r.index.add(["auth.py"])
    r.index.commit("Initial auth implementation")

    f1.write_text("def authenticate_user(token):\n    # Fix token check\n    return bool(token and token.startswith('secret_'))\n", encoding="utf-8")
    r.index.add(["auth.py"])
    r.index.commit("Fix authentication validation logic")

    return proj_dir


def test_tool_registration(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_file_history_tool(test_git_project)))
    registry.register(Tool(**create_get_recent_commits_tool(test_git_project)))
    registry.register(Tool(**create_get_last_commit_tool(test_git_project)))
    registry.register(Tool(**create_get_commit_tool(test_git_project)))
    registry.register(Tool(**create_get_file_blame_tool(test_git_project)))

    assert len(registry.list_tools()) == 5
    assert registry.get("get_file_history") is not None
    assert registry.get("get_recent_commits") is not None
    assert registry.get("get_last_commit") is not None
    assert registry.get("get_commit") is not None
    assert registry.get("get_file_blame") is not None


def test_execute_get_recent_commits_tool(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_recent_commits_tool(test_git_project)))

    res = registry.execute("get_recent_commits", {"limit": 5})
    assert res["success"] is True
    assert len(res["data"]) == 2
    assert res["data"][0]["message"] == "Fix authentication validation logic"
    assert len(res["sources"]) == 2
    assert res["sources"][0]["source_type"] == "git"


def test_execute_get_file_history_tool(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_file_history_tool(test_git_project)))

    res = registry.execute("get_file_history", {"file_path": "auth.py", "limit": 5})
    assert res["success"] is True
    assert res["data"]["file_path"] == "auth.py"
    assert len(res["data"]["commits"]) == 2
    assert res["sources"][0]["author"] == "Alice Dev"


def test_execute_get_last_commit_tool(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_last_commit_tool(test_git_project)))

    res = registry.execute("get_last_commit", {"file_path": "auth.py"})
    assert res["success"] is True
    assert res["data"]["message"] == "Fix authentication validation logic"
    assert res["sources"][0]["source_type"] == "git"


def test_execute_get_commit_tool(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_recent_commits_tool(test_git_project)))
    registry.register(Tool(**create_get_commit_tool(test_git_project)))

    rec = registry.execute("get_recent_commits", {"limit": 1})
    top_hash = rec["data"][0]["commit_hash"]

    res = registry.execute("get_commit", {"commit_hash": top_hash})
    assert res["success"] is True
    assert res["data"]["commit_hash"] == top_hash
    assert "Fix authentication validation logic" in res["data"]["message"]


def test_execute_get_file_blame_tool(test_git_project: Path):
    registry = ToolRegistry()
    registry.register(Tool(**create_get_file_blame_tool(test_git_project)))

    res = registry.execute("get_file_blame", {"file_path": "auth.py", "start_line": 1, "end_line": 2})
    assert res["success"] is True
    assert len(res["data"]["lines"]) == 2
    assert res["data"]["lines"][0]["line_number"] == 1


def test_git_tools_on_non_git_dir(tmp_path: Path):
    non_git = tmp_path / "empty"
    non_git.mkdir()

    registry = ToolRegistry()
    registry.register(Tool(**create_get_recent_commits_tool(non_git)))
    registry.register(Tool(**create_get_file_history_tool(non_git)))

    res = registry.execute("get_recent_commits", {})
    assert res["success"] is True
    assert "not a Git repository" in str(res["data"])

    res2 = registry.execute("get_file_history", {"file_path": "some_file.py"})
    assert res2["success"] is True
    assert "not a Git repository" in str(res2["data"])


def test_agent_git_integration(test_git_project: Path):
    """
    Integration test:
    User Question: "When was auth.py last changed?"
    Agent -> Calls get_last_commit("auth.py") -> Tool Result -> Mock LLM synthesizes final answer.
    """
    registry = ToolRegistry()
    registry.register(Tool(**create_get_last_commit_tool(test_git_project)))

    mock_llm = MockLLMProvider([
        # Step 1: LLM decides to call get_last_commit
        LLMChatResponse(
            content="Let me check the last commit for auth.py.",
            tool_calls=[
                ToolCall(
                    id="call_git_1",
                    name="get_last_commit",
                    arguments={"file_path": "auth.py"},
                )
            ],
            finish_reason="tool_calls",
        ),
        # Step 2: LLM receives tool result and provides final answer
        LLMChatResponse(
            content="auth.py was last changed in commit 'Fix authentication validation logic' by Alice Dev.",
            tool_calls=[],
            finish_reason="stop",
        ),
    ])

    agent = CodebaseAgent(
        llm=mock_llm,
        tool_registry=registry,
        max_iterations=5,
    )

    result = agent.run("When was auth.py last changed?")
    assert "Fix authentication validation logic" in result.answer
    assert result.iterations == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool"] == "get_last_commit"
    assert len(result.sources) == 1
    assert result.sources[0]["source_type"] == "git"
    assert result.sources[0]["author"] == "Alice Dev"
