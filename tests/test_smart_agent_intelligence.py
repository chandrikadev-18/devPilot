"""
Tests for DevPilot v1.3: Smart Tool Selection & Agent Intelligence.

Verifies:
1. Intent detection
2. Correct tool selection mapping
3. Duplicate tool prevention
4. Symbol resolution context reuse
5. Impact question using get_impact and structured formatting
6. Callees question using get_callees
7. Callers question using get_callers
8. Dependencies and dependents questions
9. No unnecessary search_code after successful symbol resolution
"""

from typing import Any, Dict, List
import pytest

from app.agent.agent import CodebaseAgent
from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.state import AgentState
from app.agent.tool_registry import Tool, ToolRegistry
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall


class MockSequenceLLM(LLMProvider):
    """Mock LLM returning a canned sequence of responses."""

    def __init__(self, responses: List[LLMChatResponse]):
        self.responses = list(responses)
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-smart-agent"

    def chat(self, messages: List[Dict[str, Any]], tools: Any = None) -> LLMChatResponse:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMChatResponse(content="")


def test_intent_detection_patterns():
    """Verifies intent classification across common question patterns."""
    # 1. IMPACT
    c1 = classify_question_intent("What could be affected if build changes?")
    assert c1.intent == QuestionIntent.IMPACT
    assert c1.target_symbol == "build"
    assert "get_impact" in c1.preferred_tools

    c2 = classify_question_intent("What is the impact of changing GraphBuilder.build?")
    assert c2.intent == QuestionIntent.IMPACT
    assert c2.target_symbol == "GraphBuilder.build"

    # 2. CALLEES
    c3 = classify_question_intent("What functions does build call?")
    assert c3.intent == QuestionIntent.CALLEES
    assert c3.target_symbol == "build"
    assert "get_callees" in c3.preferred_tools

    # 3. CALLERS
    c4 = classify_question_intent("Who calls build?")
    assert c4.intent == QuestionIntent.CALLERS
    assert c4.target_symbol == "build"
    assert "get_callers" in c4.preferred_tools

    c5 = classify_question_intent("Where is build used?")
    assert c5.intent == QuestionIntent.CALLERS
    assert c5.target_symbol == "build"

    # 4. DEPENDENCIES
    c6 = classify_question_intent("What does build depend on?")
    assert c6.intent == QuestionIntent.DEPENDENCIES
    assert c6.target_symbol == "build"
    assert "get_dependencies" in c6.preferred_tools

    # 5. DEPENDENTS
    c7 = classify_question_intent("What depends on build?")
    assert c7.intent == QuestionIntent.DEPENDENTS
    assert c7.target_symbol == "build"
    assert "get_dependents" in c7.preferred_tools

    # 6. EXPLANATION
    c8 = classify_question_intent("Explain the build function")
    assert c8.intent == QuestionIntent.EXPLANATION
    assert c8.target_symbol == "build"
    assert "read_file" in c8.preferred_tools


def test_duplicate_tool_prevention():
    """Verifies that calling the same tool with identical arguments is not re-executed."""
    exec_count = 0

    def mock_get_impact(symbol: str, depth: int = 2):
        nonlocal exec_count
        exec_count += 1
        return {
            "symbol": symbol,
            "depth": depth,
            "total_impacted": 2,
            "direct_callers": [{"name": "caller_1", "file_path": "app/main.py", "start_line": 10}],
            "indirect_callers": [{"name": "caller_2", "file_path": "app/cli.py", "start_line": 20, "depth": 2}],
            "impacted_files": ["app/main.py", "app/cli.py"],
        }

    registry = ToolRegistry()
    registry.register(Tool(
        name="get_impact",
        description="Impact analysis",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=mock_get_impact,
    ))

    # Sequence where LLM attempts duplicate get_impact calls
    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="get_impact", arguments={"symbol": "GraphBuilder.build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_impact", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What could be affected if build changes?")

    assert exec_count == 1  # Tool was executed only once
    assert "## Impact Analysis" in result.answer


def test_symbol_resolution_context_reuse():
    """Verifies that resolved canonical symbol names are reused across tools."""
    recorded_symbol_passed = []

    def mock_find_symbol(symbol_name: str):
        return [
            {
                "symbol_name": "build",
                "symbol_type": "method",
                "parent_symbol": "GraphBuilder",
                "file_path": "app/graph/builder.py",
                "start_line": 38,
                "end_line": 328,
            }
        ]

    def mock_get_callees(symbol: str):
        recorded_symbol_passed.append(symbol)
        return {
            "symbol": symbol,
            "callees": [{"name": "scan", "file_path": "app/scanner.py", "start_line": 10}],
        }

    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=mock_find_symbol,
    ))
    registry.register(Tool(
        name="get_callees",
        description="Get callees",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=mock_get_callees,
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            # LLM passes bare "build", agent normalizes it to "GraphBuilder.build"
            tool_calls=[ToolCall(id="c2", name="get_callees", arguments={"symbol": "build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What functions does build call?")

    assert recorded_symbol_passed == ["GraphBuilder.build"]
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert len(result.tool_calls) == 2


def test_no_unnecessary_search_after_symbol_resolution():
    """Verifies that search_code is blocked/intercepted after find_symbol successfully resolves."""
    search_executed = False

    def mock_find_symbol(symbol_name: str):
        return [
            {
                "symbol_name": "build",
                "parent_symbol": "GraphBuilder",
                "file_path": "app/graph/builder.py",
                "start_line": 38,
                "end_line": 328,
            }
        ]

    def mock_search_code(query: str):
        nonlocal search_executed
        search_executed = True
        return []

    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=mock_find_symbol,
    ))
    registry.register(Tool(
        name="search_code",
        description="Search code",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        func=mock_search_code,
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="search_code", arguments={"query": "def build("})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("Explain the build function")

    assert search_executed is False  # search_code was blocked because symbol was resolved


def test_impact_question_using_get_impact():
    """Verifies that impact questions execute get_impact and produce formatted direct/indirect breakdown."""
    def mock_find_symbol(symbol_name: str):
        return [
            {
                "symbol_name": "build",
                "parent_symbol": "GraphBuilder",
                "file_path": "app/graph/builder.py",
                "start_line": 38,
                "end_line": 328,
            }
        ]

    def mock_get_impact(symbol: str, depth: int = 2):
        return {
            "symbol": symbol,
            "depth": depth,
            "total_impacted": 3,
            "direct_callers": [
                {"name": "_resolve_graph", "file_path": "app/agent/tools.py", "start_line": 700},
                {"name": "_load_or_build_graph", "file_path": "app/main.py", "start_line": 1070},
            ],
            "indirect_callers": [
                {"name": "run_graph_info", "file_path": "app/main.py", "start_line": 1130, "depth": 2},
            ],
            "impacted_files": ["app/agent/tools.py", "app/main.py"],
        }

    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=mock_find_symbol,
    ))
    registry.register(Tool(
        name="get_impact",
        description="Get impact",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=mock_get_impact,
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_impact", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What could be affected if build changes?")

    assert len(result.tool_calls) == 2
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert "## Impact Analysis" in result.answer
    assert "### Direct Impact" in result.answer
    assert "- `_resolve_graph`" in result.answer
    assert "### Indirect Impact" in result.answer
    assert "- `run_graph_info`" in result.answer
    assert "### Impacted Areas" in result.answer
    assert "### Recommendation" in result.answer


def test_callees_question_using_get_callees():
    """Verifies that callees questions execute find_symbol + get_callees and stop in 2 tool calls."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: [{"symbol_name": "build", "parent_symbol": "GraphBuilder", "file_path": "app/graph/builder.py"}],
    ))
    registry.register(Tool(
        name="get_callees",
        description="Get callees",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=lambda symbol: {"symbol": symbol, "callees": [{"name": "scan", "file_path": "app/scanner.py", "start_line": 39}]},
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_callees", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What functions does build call?")

    assert len(result.tool_calls) == 2
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert "scan" in result.answer


def test_callers_question_using_get_callers():
    """Verifies that callers questions execute find_symbol + get_callers and stop in 2 tool calls."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: [{"symbol_name": "build", "parent_symbol": "GraphBuilder", "file_path": "app/graph/builder.py"}],
    ))
    registry.register(Tool(
        name="get_callers",
        description="Get callers",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=lambda symbol: {"symbol": symbol, "callers": [{"name": "_resolve_graph", "file_path": "app/agent/tools.py", "start_line": 700}]},
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_callers", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("Who calls build?")

    assert len(result.tool_calls) == 2
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert "_resolve_graph" in result.answer


def test_dependencies_question_using_get_dependencies():
    """Verifies that dependencies questions execute find_symbol + get_dependencies."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: [{"symbol_name": "build", "parent_symbol": "GraphBuilder", "file_path": "app/graph/builder.py"}],
    ))
    registry.register(Tool(
        name="get_dependencies",
        description="Get dependencies",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=lambda symbol: {"symbol": symbol, "dependencies": [{"name": "ASTExtractor.extract", "file_path": "app/graph/extractor.py", "start_line": 20}]},
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_dependencies", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What does build depend on?")

    assert len(result.tool_calls) == 2
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert "ASTExtractor" in result.answer


def test_dependents_question_using_get_dependents():
    """Verifies that dependents questions execute find_symbol + get_dependents."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: [{"symbol_name": "build", "parent_symbol": "GraphBuilder", "file_path": "app/graph/builder.py"}],
    ))
    registry.register(Tool(
        name="get_dependents",
        description="Get dependents",
        parameters={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        func=lambda symbol: {"symbol": symbol, "dependents": [{"name": "run_graph_build", "file_path": "app/main.py", "start_line": 1080}]},
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="get_dependents", arguments={"symbol": "GraphBuilder.build"})],
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("What depends on build?")

    assert len(result.tool_calls) == 2
    assert result.stopped_reason in ("intent_target_achieved", "completed", "max_iterations_reached")
    assert "run_graph_build" in result.answer


def test_definition_question_using_find_symbol():
    """Verifies that definition questions execute only find_symbol in 1 tool call."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: [{"symbol_name": "build", "parent_symbol": "GraphBuilder", "file_path": "app/graph/builder.py", "start_line": 38, "end_line": 328}],
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"})],
        ),
        LLMChatResponse(
            content="`GraphBuilder.build` is defined in `app/graph/builder.py` at lines 38-328.",
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=3)
    result = agent.run("Where is build defined?")

    assert len(result.tool_calls) == 1
    assert "GraphBuilder.build" in result.answer
    assert "app/graph/builder.py" in result.answer


def test_tool_budget_enforcement():
    """Verifies that tool call count never exceeds MAX_TOOL_CALLS budget."""
    call_counter = 0

    def dummy_tool(query: str):
        nonlocal call_counter
        call_counter += 1
        return {"data": "ok", "sources": []}

    registry = ToolRegistry()
    registry.register(Tool(
        name="search_code",
        description="Search code",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        func=dummy_tool,
    ))

    llm = MockSequenceLLM([
        LLMChatResponse(content="", tool_calls=[ToolCall(id="c1", name="search_code", arguments={"query": "q1"})]),
        LLMChatResponse(content="", tool_calls=[ToolCall(id="c2", name="search_code", arguments={"query": "q2"})]),
        LLMChatResponse(content="", tool_calls=[ToolCall(id="c3", name="search_code", arguments={"query": "q3"})]),
        LLMChatResponse(content="", tool_calls=[ToolCall(id="c4", name="search_code", arguments={"query": "q4"})]),
        LLMChatResponse(content="", tool_calls=[ToolCall(id="c5", name="search_code", arguments={"query": "q5"})]),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_tool_calls=4, max_iterations=10)
    result = agent.run("Find all authentication mechanisms")

    assert len(result.tool_calls) <= 4
    assert result.stopped_reason in ("max_tool_calls_reached", "completed")


def test_strip_thinking_tags_in_agent_response():
    """Verifies that <think> and <thought> tags are strictly stripped from final answers."""
    registry = ToolRegistry()
    llm = MockSequenceLLM([
        LLMChatResponse(
            content="<think>\nInternal reasoning step...\nEvaluating graph nodes...\n</think>\n\nAnalysis:\nSymbol: GraphBuilder.build\nFile: app/graph/builder.py\nLines: 38-328"
        ),
    ])

    agent = CodebaseAgent(llm=llm, tool_registry=registry, max_iterations=1)
    result = agent.run("Where is build defined?")

    assert "<think>" not in result.answer
    assert "</think>" not in result.answer
    assert "Internal reasoning" not in result.answer
    assert "Symbol: GraphBuilder.build" in result.answer
