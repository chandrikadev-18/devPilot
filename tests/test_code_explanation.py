"""
Tests for DevPilot v1.1: AI-Powered Code Explanation.

Verifies:
1. Symbol resolution with bare and qualified/dotted names (find_symbol)
2. Sliced source code retrieval (read_file with start_line/end_line)
3. Agent code explanation orchestration and structured answer synthesis
4. Non-hallucination / explicit absence handling
5. Preservation of v1.0 graph query workflows
"""

from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import pytest

from app.agent.agent import CodebaseAgent
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools import (
    create_find_symbol_tool,
    create_get_callees_tool,
    create_get_callers_tool,
    create_get_dependencies_tool,
    create_get_file_dependencies_tool,
    create_get_impact_tool,
    create_read_file_tool,
    create_search_code_tool,
)
from app.graph.builder import GraphBuilder
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall
from app.search.semantic_search import SemanticSearcher


class MockLLM(LLMProvider):
    def __init__(self, responses: List[LLMChatResponse]):
        self.responses = list(responses)
        self.call_count = 0
        self.recorded_messages = []

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-explanation-model"

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMChatResponse:
        self.recorded_messages.append(messages)
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMChatResponse(content="Fallback synthesized response.")


@pytest.fixture
def sample_code_tree(tmp_path):
    """Creates a realistic code repository structure for testing."""
    pkg = tmp_path / "app" / "graph"
    pkg.mkdir(parents=True, exist_ok=True)

    builder_code = '''"""Graph builder module."""
from app.graph.store import GraphStore

class GraphBuilder:
    def __init__(self):
        self.store = GraphStore()

    def build(self, directory: str) -> GraphStore:
        """Builds dependency graph for directory."""
        if not directory:
            raise ValueError("Directory cannot be empty")
        self.scan_files(directory)
        self.extract_symbols()
        return self.store

    def scan_files(self, directory: str):
        pass

    def extract_symbols(self):
        pass


def build_default_graph(directory: str = ".") -> GraphStore:
    builder = GraphBuilder()
    return builder.build(directory)
'''
    (pkg / "builder.py").write_text(builder_code, encoding="utf-8")

    cli_code = '''"""CLI entry point."""
from app.graph.builder import build_default_graph

def run_cli():
    graph = build_default_graph(".")
    print("Graph built")
'''
    (tmp_path / "app" / "cli.py").write_text(cli_code, encoding="utf-8")

    return tmp_path


def test_find_symbol_bare_name(sample_code_tree):
    """Verifies find_symbol finds functions and methods by simple name."""
    find_tool = create_find_symbol_tool(project_root=sample_code_tree)
    res = find_tool["func"](symbol_name="build")

    assert res["data"] != f"Symbol 'build' was not found in the codebase."
    matches = res["data"]
    assert isinstance(matches, list)
    names = [m["symbol_name"] for m in matches]
    assert "build" in names
    types = [m["symbol_type"] for m in matches]
    assert "method" in types


def test_find_symbol_qualified_name(sample_code_tree):
    """Verifies find_symbol resolves dotted/qualified symbols like GraphBuilder.build or app.graph.builder.build."""
    find_tool = create_find_symbol_tool(project_root=sample_code_tree)

    # Qualified with Class name
    res1 = find_tool["func"](symbol_name="GraphBuilder.build")
    assert isinstance(res1["data"], list)
    assert len(res1["data"]) >= 1
    assert res1["data"][0]["symbol_name"] == "build"
    assert res1["data"][0]["parent_symbol"] == "GraphBuilder"

    # Qualified with Module path
    res2 = find_tool["func"](symbol_name="app.graph.builder.build_default_graph")
    assert isinstance(res2["data"], list)
    assert len(res2["data"]) >= 1
    assert res2["data"][0]["symbol_name"] == "build_default_graph"


def test_find_symbol_not_found(sample_code_tree):
    """Verifies clean message when symbol does not exist."""
    find_tool = create_find_symbol_tool(project_root=sample_code_tree)
    res = find_tool["func"](symbol_name="non_existent_symbol_xyz")
    assert "was not found" in res["data"]
    assert res["sources"] == []


def test_read_file_line_slicing(sample_code_tree):
    """Verifies read_file can read specific line ranges."""
    read_tool = create_read_file_tool(project_root=sample_code_tree)

    # Full read
    full_res = read_tool["func"](file_path="app/graph/builder.py")
    assert full_res["data"]["start_line"] == 1
    assert full_res["data"]["end_line"] == full_res["data"]["lines"]

    # Sliced read for lines 8 to 15 (def build)
    sliced_res = read_tool["func"](file_path="app/graph/builder.py", start_line=8, end_line=15)
    data = sliced_res["data"]
    assert data["start_line"] == 8
    assert data["end_line"] == 15
    assert "def build(self, directory: str) -> GraphStore:" in data["content"]
    assert "from app.graph.store import GraphStore" not in data["content"]
    assert sliced_res["sources"][0]["start_line"] == 8
    assert sliced_res["sources"][0]["end_line"] == 15


def test_code_explanation_agent_orchestration(sample_code_tree):
    """
    Verifies agent end-to-end code explanation workflow:
    1. Agent resolves symbol via find_symbol
    2. Agent inspects code via read_file
    3. Agent inspects callers / callees via graph tools
    4. Agent synthesizes structured explanation
    """
    graph = GraphBuilder().build(sample_code_tree)
    registry = ToolRegistry()

    find_spec = create_find_symbol_tool(project_root=sample_code_tree)
    read_spec = create_read_file_tool(project_root=sample_code_tree)
    callees_spec = create_get_callees_tool(graph=graph, project_root=sample_code_tree)
    callers_spec = create_get_callers_tool(graph=graph, project_root=sample_code_tree)
    dep_spec = create_get_dependencies_tool(graph=graph, project_root=sample_code_tree)

    registry.register(Tool(**find_spec))
    registry.register(Tool(**read_spec))
    registry.register(Tool(**callees_spec))
    registry.register(Tool(**callers_spec))
    registry.register(Tool(**dep_spec))

    # Mock multi-step reasoning
    mock_responses = [
        # Step 1: LLM locates symbol
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"}),
            ]
        ),
        # Step 2: LLM reads targeted source and queries graph callees + callers
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c2", name="read_file", arguments={"file_path": "app/graph/builder.py", "start_line": 8, "end_line": 15}),
                ToolCall(id="c3", name="get_callees", arguments={"symbol": "build"}),
                ToolCall(id="c4", name="get_callers", arguments={"symbol": "build"}),
            ]
        ),
        # Step 3: LLM provides comprehensive structured explanation
        LLMChatResponse(
            content="""## build()

**Location**
`app/graph/builder.py:8`

**Purpose**
Builds the project's dependency graph for a given directory path.

**Signature**
```python
def build(self, directory: str) -> GraphStore:
```

**Parameters & Return Value**
- `directory` (str): Root path to scan and analyze.
- Return (`GraphStore`): The populated dependency graph store.

**Main Responsibilities & Execution Steps**
1. Validates that the input directory path is non-empty.
2. Scans files via `scan_files(directory)`.
3. Extracts AST symbols via `extract_symbols()`.
4. Returns the accumulated `self.store`.

**Call Hierarchy & Graph Context**
- **Callees**: `scan_files`, `extract_symbols`
- **Callers**: `build_default_graph`

**Dependencies & Classes Used**
- `GraphStore` from `app.graph.store`

**Side Effects & Error Handling**
- Raises `ValueError("Directory cannot be empty")` if `directory` is falsy.
- Modifies internal state `self.store`.

**Testing Considerations**
- Test with valid directory paths.
- Test edge case with empty string to verify `ValueError` is raised.
- Mock `scan_files` and `extract_symbols` during unit tests.
"""
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain the build function")

    assert "## build()" in result.answer
    assert "app/graph/builder.py" in result.answer
    assert "def build" in result.answer
    assert "scan_files" in result.answer
    assert "build_default_graph" in result.answer
    assert "ValueError" in result.answer
    assert "Testing Considerations" in result.answer

    tool_names = [tc["tool"] for tc in result.tool_calls]
    assert "find_symbol" in tool_names
    assert "read_file" in tool_names
    assert "get_callees" in tool_names
    assert "get_callers" in tool_names


def test_code_explanation_non_existent_or_missing_info(sample_code_tree):
    """Verifies that missing information or absent callers are explicitly stated without inventing facts."""
    graph = GraphBuilder().build(sample_code_tree)
    registry = ToolRegistry()

    find_spec = create_find_symbol_tool(project_root=sample_code_tree)
    callers_spec = create_get_callers_tool(graph=graph, project_root=sample_code_tree)
    registry.register(Tool(**find_spec))
    registry.register(Tool(**callers_spec))

    mock_responses = [
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "run_cli"}),
                ToolCall(id="c2", name="get_callers", arguments={"symbol": "run_cli"}),
            ]
        ),
        LLMChatResponse(
            content="""## run_cli()

**Location**
`app/cli.py:4`

**Purpose**
Entry point executing the CLI command.

**Callers**
No direct callers found in the codebase.

**Error Handling**
No explicit try/except or error handling visible in this function.
"""
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain run_cli")
    assert "No direct callers found" in result.answer
    assert "No explicit try/except" in result.answer


def test_exact_symbol_matching_priority(tmp_path):
    """
    Verifies that find_symbol strictly prioritizes exact symbol names:
    - query 'build' matches 'build' and NOT 'build_chunk_payload' or 'build_embedding_text'
    - query 'build_chunk_payload' matches 'build_chunk_payload' and NOT 'build'
    - query 'build_embedding_text' matches 'build_embedding_text' and NOT 'build'
    """
    (tmp_path / "mod_a.py").write_text("""
def build(directory: str):
    return "built"

def build_chunk_payload(chunk):
    return {"chunk": chunk}

def build_embedding_text(text):
    return f"embed:{text}"
""", encoding="utf-8")

    find_tool = create_find_symbol_tool(project_root=tmp_path)

    # 1. Query: 'build'
    res_build = find_tool["func"](symbol_name="build")
    assert isinstance(res_build["data"], list)
    names_build = [m["symbol_name"] for m in res_build["data"]]
    assert "build" in names_build
    assert "build_chunk_payload" not in names_build
    assert "build_embedding_text" not in names_build

    # 2. Query: 'build_chunk_payload'
    res_chunk = find_tool["func"](symbol_name="build_chunk_payload")
    assert isinstance(res_chunk["data"], list)
    names_chunk = [m["symbol_name"] for m in res_chunk["data"]]
    assert "build_chunk_payload" in names_chunk
    assert "build" not in names_chunk

    # 3. Query: 'build_embedding_text'
    res_embed = find_tool["func"](symbol_name="build_embedding_text")
    assert isinstance(res_embed["data"], list)
    names_embed = [m["symbol_name"] for m in res_embed["data"]]
    assert "build_embedding_text" in names_embed
    assert "build" not in names_embed


def test_strip_thinking_and_tool_tags():
    """Verifies that strip_thinking_and_tool_tags strips internal <think> and <tool_call> markup."""
    from app.llm import strip_thinking_and_tool_tags

    raw_text = """<think>
Let's see: the user wants an explanation of the build function.
I should look up the file app/graph/builder.py.
</think>
## build()

**Location**
`app/graph/builder.py:46`
"""
    cleaned = strip_thinking_and_tool_tags(raw_text)
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned
    assert "Let's see" not in cleaned
    assert "## build()" in cleaned
    assert "`app/graph/builder.py:46`" in cleaned

    # Also test tool_call tags
    tool_markup = """<tool_call>
{"name": "find_symbol", "arguments": {"symbol_name": "build"}}
</tool_call>
Final explanation text."""
    cleaned_tool = strip_thinking_and_tool_tags(tool_markup)
    assert "<tool_call>" not in cleaned_tool
    assert "Final explanation text." in cleaned_tool


def test_agent_strips_thinking_tags_from_final_answer(sample_code_tree):
    """Verifies that an agent run with thinking markup yields clean answer."""
    registry = ToolRegistry()
    find_spec = create_find_symbol_tool(project_root=sample_code_tree)
    registry.register(Tool(**find_spec))

    mock_responses = [
        LLMChatResponse(
            content="""<think>
Analyzing the build function...
</think>
## build()
Builds the dependency graph."""
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain the build function")
    assert "<think>" not in result.answer
    assert "</think>" not in result.answer
    assert "Analyzing the build function" not in result.answer
    assert "## build()" in result.answer


def test_duplicate_tool_call_protection_single_execution(sample_code_tree):
    """
    Verifies that calling the exact same tool with identical arguments
    executes the underlying tool only once and reuses the result.
    """
    registry = ToolRegistry()
    raw_read_tool = create_read_file_tool(project_root=sample_code_tree)
    mock_execute = MagicMock(side_effect=raw_read_tool["func"])
    read_tool_spec = dict(raw_read_tool)
    read_tool_spec["func"] = mock_execute
    registry.register(Tool(**read_tool_spec))

    mock_responses = [
        # Step 1: Request read_file for builder.py
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="read_file", arguments={"file_path": "app/graph/builder.py"}),
            ]
        ),
        # Step 2: Model mistakenly requests the EXACT same tool call again
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c2", name="read_file", arguments={"file_path": "app/graph/builder.py"}),
            ]
        ),
        # Step 3: Synthesis
        LLMChatResponse(
            content="## build()\nExplanation based on single execution."
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain the build function")

    # Underlying tool was executed exactly ONCE
    assert mock_execute.call_count == 1
    assert "## build()" in result.answer


def test_different_tool_arguments_are_both_executed(sample_code_tree):
    """
    Verifies that different arguments to the same tool are NOT treated as duplicates
    and both execute normally.
    """
    (sample_code_tree / "app" / "graph" / "store.py").write_text("class GraphStore: pass", encoding="utf-8")

    registry = ToolRegistry()
    raw_read_tool = create_read_file_tool(project_root=sample_code_tree)
    mock_execute = MagicMock(side_effect=raw_read_tool["func"])
    read_tool_spec = dict(raw_read_tool)
    read_tool_spec["func"] = mock_execute
    registry.register(Tool(**read_tool_spec))

    mock_responses = [
        # Call 1: read builder.py
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="read_file", arguments={"file_path": "app/graph/builder.py"}),
                ToolCall(id="c2", name="read_file", arguments={"file_path": "app/graph/store.py"}),
            ]
        ),
        LLMChatResponse(
            content="## Explanation of builder and store."
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain builder and store")

    # Both distinct file reads were executed
    assert mock_execute.call_count == 2
    assert "Explanation of builder and store" in result.answer


def test_find_symbol_to_synthesis_workflow(sample_code_tree):
    """
    Verifies optimal explanation workflow:
    find_symbol -> read_file -> synthesis without repetitive tool loops.
    """
    registry = ToolRegistry()
    find_spec = create_find_symbol_tool(project_root=sample_code_tree)
    read_spec = create_read_file_tool(project_root=sample_code_tree)
    registry.register(Tool(**find_spec))
    registry.register(Tool(**read_spec))

    mock_responses = [
        # Step 1: find_symbol
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c1", name="find_symbol", arguments={"symbol_name": "build"}),
            ]
        ),
        # Step 2: read_file
        LLMChatResponse(
            tool_calls=[
                ToolCall(id="c2", name="read_file", arguments={"file_path": "app/graph/builder.py", "start_line": 67, "end_line": 78}),
            ]
        ),
        # Step 3: Synthesis
        LLMChatResponse(
            content="## build()\nDetailed explanation of build method."
        ),
    ]

    mock_llm = MockLLM(mock_responses)
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    result = agent.run("Explain the build function")

    read_calls = [tc for tc in result.tool_calls if tc["tool"] == "read_file"]
    assert len(read_calls) == 1
    assert "## build()" in result.answer


