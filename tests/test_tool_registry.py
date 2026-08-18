"""
Tests for Tool Registry and Schema Validation.
"""

import pytest

from app.agent.tool_registry import Tool, ToolRegistry, ToolValidationError


def dummy_search(query: str, top_k: int = 5):
    return {"data": f"Results for {query}", "sources": []}


@pytest.fixture
def sample_registry():
    registry = ToolRegistry()
    tool = Tool(
        name="search_code",
        description="Searches code",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1},
            },
            "required": ["query"],
        },
        func=dummy_search,
        safety_level="read_only",
    )
    registry.register(tool)
    return registry


def test_registry_register_and_get(sample_registry):
    """Verifies tool registration and retrieval."""
    tool = sample_registry.get("search_code")
    assert tool is not None
    assert tool.name == "search_code"
    assert sample_registry.get("unknown_tool") is None


def test_registry_get_specs(sample_registry):
    """Verifies generation of OpenAI/Groq function calling specs."""
    specs = sample_registry.get_tool_specs()
    assert len(specs) == 1
    assert specs[0]["type"] == "function"
    assert specs[0]["function"]["name"] == "search_code"
    assert "query" in specs[0]["function"]["parameters"]["properties"]


def test_registry_execute_success(sample_registry):
    """Verifies successful tool execution."""
    res = sample_registry.execute("search_code", {"query": "auth handling"})
    assert res["success"] is True
    assert res["tool"] == "search_code"
    assert "Results for auth handling" in res["data"]
    assert res["error"] is None


def test_registry_execute_unknown_tool(sample_registry):
    """Verifies executing unknown tool returns error structure."""
    res = sample_registry.execute("unknown_tool", {})
    assert res["success"] is False
    assert "Unknown tool 'unknown_tool'" in res["error"]


def test_registry_validation_missing_required(sample_registry):
    """Verifies missing required parameters are rejected."""
    res = sample_registry.execute("search_code", {})
    assert res["success"] is False
    assert "Missing required parameter 'query'" in res["error"]


def test_registry_validation_wrong_type(sample_registry):
    """Verifies invalid parameter types are rejected."""
    res = sample_registry.execute("search_code", {"query": 12345})
    assert res["success"] is False
    assert "must be a string" in res["error"]


def test_registry_validation_minimum_constraint(sample_registry):
    """Verifies numeric minimum constraints are enforced."""
    res = sample_registry.execute("search_code", {"query": "test", "top_k": 0})
    assert res["success"] is False
    assert "must be >= 1" in res["error"]


def test_reject_non_read_only_tool():
    """Verifies tools with non-read_only safety level are rejected at registration."""
    registry = ToolRegistry()
    unsafe_tool = Tool(
        name="delete_file",
        description="Unsafe tool",
        parameters={"type": "object"},
        func=lambda: None,
        safety_level="destructive",
    )
    with pytest.raises(ValueError) as exc:
        registry.register(unsafe_tool)
    assert "Only read_only tools are permitted" in str(exc.value)
