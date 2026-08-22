"""
Tests for DevPilot v1.3: Presentation-Ready CLI and Agent Presentation.

Verifies:
1. Demo command execution (run_demo)
2. Professional CLI presentation for graph commands
3. Structured code explanation output formatting
4. Explicit symbol-not-found suggestions
5. Duplicate tool-call handling and reuse
"""

import io
from pathlib import Path
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from app.agent.agent import CodebaseAgent
from app.agent.state import AgentState
from app.agent.tool_registry import Tool, ToolRegistry
from app.graph.builder import GraphBuilder
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall
from app.main import (
    run_demo,
    run_graph_callees,
    run_graph_callers,
    run_graph_dependencies,
    run_graph_impact,
    run_graph_info,
)


class MockLLM(LLMProvider):
    def __init__(self, responses: List[LLMChatResponse]):
        self.responses = list(responses)
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-presentation-model"

    def chat(self, messages: List[Dict[str, Any]], tools: Any = None) -> LLMChatResponse:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMChatResponse(content="Structured presentation fallback.")


@pytest.fixture
def sample_demo_project(tmp_path):
    """Creates a sample project for testing graph and presentation commands."""
    pkg = tmp_path / "app" / "graph"
    pkg.mkdir(parents=True, exist_ok=True)

    builder_code = '''"""Graph builder module."""
from app.graph.store import GraphStore

class GraphBuilder:
    """Builds a complete dependency graph for a Python project."""
    def __init__(self):
        self.store = GraphStore()

    def build(self, directory: str) -> GraphStore:
        """Builds dependency graph for directory."""
        # Step 1: Scan files
        self.scan_files(directory)
        # Step 2: Extract symbols
        self.extract_symbols()
        return self.store

    def scan_files(self, directory: str):
        pass

    def extract_symbols(self):
        pass
'''
    (pkg / "builder.py").write_text(builder_code, encoding="utf-8")

    cli_code = '''"""CLI entry point."""
from app.graph.builder import GraphBuilder

def run_cli():
    builder = GraphBuilder()
    graph = builder.build(".")
    print("Graph built")
'''
    (tmp_path / "app" / "cli.py").write_text(cli_code, encoding="utf-8")

    return tmp_path


def test_run_demo_command(sample_demo_project, monkeypatch):
    """Verifies that run_demo executes the full 7-step presentation without errors."""
    output_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_capture)

    run_demo(project_dir=str(sample_demo_project))

    output = output_capture.getvalue()
    assert "DevPilot v1.3 - Demonstration" in output
    assert "[1/7] Building Code Dependency Graph..." in output
    assert "[2/7] Dependency Graph Overview:" in output
    assert "[3/7] Finding Symbol: GraphBuilder.build" in output
    assert "[4/7] Outgoing Calls from 'build':" in output
    assert "[5/7] Direct Callers of 'build':" in output
    assert "[6/7] Static Impact Analysis for 'build'" in output
    assert "[7/7] Code Explanation: GraphBuilder.build" in output
    assert "Demo completed successfully." in output


def test_graph_info_presentation(sample_demo_project, monkeypatch):
    """Verifies graph-info output formatting and DevPilot v1.3 banner."""
    output_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_capture)

    run_graph_info(project_dir=str(sample_demo_project))

    output = output_capture.getvalue()
    assert "DevPilot v1.3 - Dependency Graph Info" in output
    assert "Total Nodes:" in output
    assert "Total Edges:" in output


def test_graph_callers_presentation(sample_demo_project, monkeypatch):
    """Verifies graph-callers output formatting."""
    output_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_capture)

    run_graph_callers(symbol="build", project_dir=str(sample_demo_project))

    output = output_capture.getvalue()
    assert "DevPilot v1.3 - Code Callers Analysis" in output
    assert "Symbol: build" in output
    assert "Callers (" in output
    assert "run_cli" in output


def test_graph_callees_presentation(sample_demo_project, monkeypatch):
    """Verifies graph-callees output formatting."""
    output_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_capture)

    run_graph_callees(symbol="build", project_dir=str(sample_demo_project))

    output = output_capture.getvalue()
    assert "DevPilot v1.3 - Outgoing Calls Analysis" in output
    assert "Symbol: build" in output
    assert "Calls (" in output


def test_graph_impact_presentation(sample_demo_project, monkeypatch):
    """Verifies graph-impact output formatting."""
    output_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_capture)

    run_graph_impact(symbol="build", depth=2, project_dir=str(sample_demo_project))

    output = output_capture.getvalue()
    assert "DevPilot v1.3 - Static Impact Analysis" in output
    assert "Target Symbol:          build (Depth: 2)" in output
    assert "Total Affected Callers:" in output
    assert "Direct Callers" in output


def test_agent_symbol_not_found_handling():
    """Verifies structured output when a symbol is not found."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="find_symbol",
        description="Find symbol",
        parameters={"type": "object", "properties": {"symbol_name": {"type": "string"}}, "required": ["symbol_name"]},
        func=lambda symbol_name: {"data": f"Symbol '{symbol_name}' was not found in the codebase.", "sources": []},
    ))

    # Empty mock responses to trigger fallback explanation
    mock_llm = MockLLM([])
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    state = AgentState(
        user_question="Explain non_existent_symbol",
        tool_calls=[{"tool": "find_symbol", "arguments": {"symbol_name": "non_existent_symbol"}}],
        tool_results=[{"success": True, "data": "Symbol 'non_existent_symbol' was not found in the codebase."}],
    )

    fallback = agent._generate_fallback_explanation(state)
    assert "Symbol not found:" in fallback
    assert "non_existent_symbol" in fallback
    assert "Suggestions:" in fallback
    assert "- Check the symbol name" in fallback
    assert "- Try a fully qualified name" in fallback


def test_agent_structured_code_explanation_fallback():
    """Verifies structured fallback formatting for found code symbols."""
    registry = ToolRegistry()
    mock_llm = MockLLM([])
    agent = CodebaseAgent(llm=mock_llm, tool_registry=registry)

    state = AgentState(
        user_question="Explain build",
        tool_calls=[{"tool": "find_symbol", "arguments": {"symbol_name": "build"}}],
        tool_results=[
            {
                "success": True,
                "data": [
                    {
                        "symbol_name": "build",
                        "symbol_type": "method",
                        "parent_symbol": "GraphBuilder",
                        "file_path": "app/graph/builder.py",
                        "start_line": 38,
                        "end_line": 328,
                        "code": 'def build(self, directory: str):\n    """Builds complete dependency graph."""\n    # Step 1: Scan files\n    # Step 2: Extract AST\n    pass',
                    }
                ],
            },
            {
                "success": True,
                "data": {
                    "symbol": "build",
                    "callees": [{"name": "scan", "file_path": "app/scanner.py", "start_line": 10}],
                },
            },
            {
                "success": True,
                "data": {
                    "symbol": "build",
                    "callers": [{"name": "run_cli", "file_path": "app/main.py", "start_line": 50}],
                },
            },
        ],
    )

    fallback = agent._generate_fallback_explanation(state)
    assert "Analysis:" in fallback
    assert "Symbol: GraphBuilder.build" in fallback
    assert "File: app/graph/builder.py" in fallback
    assert "Lines: 38-328" in fallback
    assert "Purpose:" in fallback
    assert "Key Responsibilities:" in fallback
    assert "Dependencies:" in fallback
    assert "- scan" in fallback
    assert "Impact:" in fallback
    assert "Used by:" in fallback
    assert "- run_cli" in fallback
    assert "Sources:" in fallback
    assert "app/graph/builder.py:38-328" in fallback
