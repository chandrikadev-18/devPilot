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


def test_default_tool_registry_contains_all_graph_tools():
    """Verifies that create_default_tool_registry registers all v1.0 graph tools."""
    from app.agent import create_default_tool_registry
    from app.search.semantic_search import SemanticSearcher

    mock_searcher = MagicMock(spec=SemanticSearcher)
    registry = create_default_tool_registry(searcher=mock_searcher)

    required_tools = [
        "get_callers",
        "get_callees",
        "get_dependencies",
        "get_dependents",
        "get_impact",
        "get_file_dependencies",
        "search_code",
        "read_file",
        "find_symbol",
        "get_file_structure",
    ]
    for tool_name in required_tools:
        tool = registry.get(tool_name)
        assert tool is not None, f"Tool '{tool_name}' must be registered in ToolRegistry"
        assert tool.name == tool_name


def test_agent_what_functions_does_build_call():
    """
    Deterministic unit test verifying agent uses get_callees when asked:
    'What functions does build call?'
    """
    from app.agent import create_codebase_agent
    from app.search.semantic_search import SemanticSearcher

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "builder.py").write_text("""
def scan(): pass
def extract_file(): pass
def add_node(): pass

def build():
    scan()
    extract_file()
    add_node()
""", encoding="utf-8")

        mock_searcher = MagicMock(spec=SemanticSearcher)

        step1 = LLMChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_callees_1",
                    name="get_callees",
                    arguments={"symbol": "build"},
                )
            ],
        )
        step2 = LLMChatResponse(
            content="build calls: 1. scan, 2. extract_file, 3. add_node.",
            tool_calls=[],
        )

        mock_llm = MockLLM([step1, step2])
        agent = create_codebase_agent(
            llm=mock_llm,
            searcher=mock_searcher,
            project_root=root,
        )

        result = agent.run("What functions does build call?")

        executed_tools = [tc["tool"] for tc in result.tool_calls]
        assert "get_callees" in executed_tools
        assert "find_symbol" not in executed_tools
        assert "search_code" not in executed_tools

        assert len(result.sources) >= 3
        source_names = [s["symbol_name"] for s in result.sources if s.get("source_type") == "graph"]
        assert "scan" in source_names
        assert "extract_file" in source_names
        assert "add_node" in source_names

        assert "scan" in result.answer
        assert "extract_file" in result.answer
        assert "add_node" in result.answer


def test_agent_graph_questions_suite():
    """
    Tests agent handling of:
    - What functions call build? -> get_callers
    - What does build depend on? -> get_dependencies
    - What depends on build? -> get_dependents
    - What could be affected if build changes? -> get_impact
    - What files does build depend on? -> get_file_dependencies
    """
    from app.agent import create_codebase_agent
    from app.search.semantic_search import SemanticSearcher

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "module_a.py").write_text("""
def base(): pass
def build(): base()
def caller_func(): build()
""", encoding="utf-8")

        mock_searcher = MagicMock(spec=SemanticSearcher)

        # 1. get_callers
        mock_llm1 = MockLLM([
            LLMChatResponse(tool_calls=[ToolCall(id="c1", name="get_callers", arguments={"symbol": "build"})]),
            LLMChatResponse(content="build is called by caller_func."),
        ])
        agent1 = create_codebase_agent(llm=mock_llm1, searcher=mock_searcher, project_root=root)
        res1 = agent1.run("What functions call build?")
        assert res1.tool_calls[0]["tool"] == "get_callers"
        assert "caller_func" in res1.answer

        # 2. get_dependencies
        mock_llm2 = MockLLM([
            LLMChatResponse(tool_calls=[ToolCall(id="c2", name="get_dependencies", arguments={"symbol": "build", "depth": 1})]),
            LLMChatResponse(content="build depends on base."),
        ])
        agent2 = create_codebase_agent(llm=mock_llm2, searcher=mock_searcher, project_root=root)
        res2 = agent2.run("What does build depend on?")
        assert res2.tool_calls[0]["tool"] == "get_dependencies"
        assert "base" in res2.answer

        # 3. get_dependents
        mock_llm3 = MockLLM([
            LLMChatResponse(tool_calls=[ToolCall(id="c3", name="get_dependents", arguments={"symbol": "build", "depth": 1})]),
            LLMChatResponse(content="caller_func depends on build."),
        ])
        agent3 = create_codebase_agent(llm=mock_llm3, searcher=mock_searcher, project_root=root)
        res3 = agent3.run("What depends on build?")
        assert res3.tool_calls[0]["tool"] == "get_dependents"
        assert "caller_func" in res3.answer

        # 4. get_impact
        mock_llm4 = MockLLM([
            LLMChatResponse(tool_calls=[ToolCall(id="c4", name="get_impact", arguments={"symbol": "build", "depth": 2})]),
            LLMChatResponse(content="Changing build affects caller_func."),
        ])
        agent4 = create_codebase_agent(llm=mock_llm4, searcher=mock_searcher, project_root=root)
        res4 = agent4.run("What could be affected if build changes?")
        assert res4.tool_calls[0]["tool"] == "get_impact"
        assert "caller_func" in res4.answer

        # 5. get_file_dependencies
        mock_llm5 = MockLLM([
            LLMChatResponse(tool_calls=[ToolCall(id="c5", name="get_file_dependencies", arguments={"file_path": "module_a.py"})]),
            LLMChatResponse(content="module_a.py has no external file dependencies."),
        ])
        agent5 = create_codebase_agent(llm=mock_llm5, searcher=mock_searcher, project_root=root)
        res5 = agent5.run("What files does build depend on?")
        assert res5.tool_calls[0]["tool"] == "get_file_dependencies"


def test_agent_repetition_detection():
    """Verifies that the agent loop prevents endless repeated tool calls."""
    from app.agent import create_codebase_agent
    from app.search.semantic_search import SemanticSearcher

    mock_searcher = MagicMock(spec=SemanticSearcher)
    mock_searcher.search.return_value = []

    # LLM keeps returning the exact same tool call
    repeated_responses = [
        LLMChatResponse(tool_calls=[ToolCall(id=f"call_{i}", name="search_code", arguments={"query": "def build("})])
        for i in range(10)
    ]
    mock_llm = MockLLM(repeated_responses)
    agent = create_codebase_agent(llm=mock_llm, searcher=mock_searcher, max_iterations=5)

    result = agent.run("What functions does build call?")
    assert result.stopped_reason == "repeated_tool_call"
    # Verify it stopped after detecting repeats instead of looping through all max iterations endlessly
    assert result.iterations <= 3


def test_agent_callers_and_callees_query():
    """
    Verifies that the agent handles combined caller + callee questions:
    'What are the callers and callees of GraphBuilder.build?'
    by calling find_symbol, get_callers, and get_callees and synthesizing both.
    """
    from app.agent import create_codebase_agent
    from app.agent.intent import classify_question_intent, QuestionIntent
    from app.search.semantic_search import SemanticSearcher

    question = "What are the callers and callees of GraphBuilder.build?"
    classification = classify_question_intent(question)
    assert classification.intent == QuestionIntent.CALLERS_AND_CALLEES
    assert classification.target_symbol == "GraphBuilder.build"
    assert classification.preferred_tools == ["find_symbol", "get_callers", "get_callees"]

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "builder.py").write_text("""
class GraphBuilder:
    def build(self):
        self.scan()
        return "done"

    def scan(self):
        pass

def caller_func():
    return GraphBuilder().build()
""", encoding="utf-8")

        mock_searcher = MagicMock(spec=SemanticSearcher)

        # Mock LLM calling find_symbol, get_callers, and get_callees
        step1 = LLMChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="c_find",
                    name="find_symbol",
                    arguments={"symbol_name": "GraphBuilder.build"},
                )
            ],
        )
        step2 = LLMChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="c_callers",
                    name="get_callers",
                    arguments={"symbol": "GraphBuilder.build"},
                ),
                ToolCall(
                    id="c_callees",
                    name="get_callees",
                    arguments={"symbol": "GraphBuilder.build"},
                ),
            ],
        )
        step3 = LLMChatResponse(
            content="",
            tool_calls=[],
        )

        mock_llm = MockLLM([step1, step2, step3])
        agent = create_codebase_agent(
            llm=mock_llm,
            searcher=mock_searcher,
            project_root=root,
        )

        result = agent.run(question)
        tool_names = [tc["tool"] for tc in result.tool_calls]
        assert "find_symbol" in tool_names
        assert "get_callers" in tool_names
        assert "get_callees" in tool_names
        assert "caller_func" in result.answer
        assert "scan" in result.answer
        assert "No direct callers found" not in result.answer

