"""
Tests for Graph Agent Tools and ToolRegistry Integration.
"""

from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from app.agent.agent import CodebaseAgent
from app.agent.tool_registry import ToolRegistry, Tool
from app.agent.tools import (
    create_get_callees_tool,
    create_get_callers_tool,
    create_get_dependencies_tool,
    create_get_file_dependencies_tool,
    create_get_impact_tool,
)
from app.graph.builder import GraphBuilder
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall


class MockLLM(LLMProvider):
    def __init__(self, responses: List[LLMChatResponse]):
        self.responses = responses
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMChatResponse:
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


def test_graph_tools_direct_invocation():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "service.py").write_text("""
def calculate(a, b):
    return a + b

def execute():
    return calculate(1, 2)
""", encoding="utf-8")

        graph = GraphBuilder().build(root)

        # 1. callers tool
        callers_spec = create_get_callers_tool(graph=graph, project_root=root)
        callers_res = callers_spec["func"](symbol="calculate")
        assert len(callers_res["data"]) == 1
        assert callers_res["data"][0]["name"] == "execute"
        assert callers_res["sources"][0]["source_type"] == "graph"

        # 2. callees tool
        callees_spec = create_get_callees_tool(graph=graph, project_root=root)
        callees_res = callees_spec["func"](symbol="execute")
        assert len(callees_res["data"]) == 1
        assert callees_res["data"][0]["name"] == "calculate"

        # 3. dependencies tool
        dep_spec = create_get_dependencies_tool(graph=graph, project_root=root)
        dep_res = dep_spec["func"](symbol="execute", depth=1)
        assert dep_res["data"]["total_dependencies"] == 1

        # 4. impact tool
        impact_spec = create_get_impact_tool(graph=graph, project_root=root)
        impact_res = impact_spec["func"](symbol="calculate", depth=2)
        assert impact_res["data"]["total_impacted"] == 1

        # 5. file dependencies tool
        file_spec = create_get_file_dependencies_tool(graph=graph, project_root=root)
        file_res = file_spec["func"](file_path="service.py")
        assert "service.py" in file_res["data"]["file_path"]


def test_agent_using_graph_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "math_lib.py").write_text("""
def add(a, b):
    return a + b

def add_three(a, b, c):
    return add(add(a, b), c)
""", encoding="utf-8")

        graph = GraphBuilder().build(root)
        registry = ToolRegistry()

        callers_spec = create_get_callers_tool(graph=graph, project_root=root)
        registry.register(Tool(**callers_spec))

        # Mock LLM calling get_callers then synthesizing answer
        step1 = LLMChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="get_callers",
                    arguments={"symbol": "add"},
                )
            ],
        )
        step2 = LLMChatResponse(
            content="The function `add` is directly called by `add_three` in `math_lib.py`.",
            tool_calls=[],
        )

        mock_llm = MockLLM([step1, step2])
        agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

        result = agent.run("What calls add?")
        assert "add_three" in result.answer
        assert len(result.sources) > 0
        assert result.sources[0]["source_type"] == "graph"
        assert result.sources[0]["relationship"] == "CALLER"
