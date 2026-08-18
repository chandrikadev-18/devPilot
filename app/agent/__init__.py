"""
DevPilot Agent Module.

Provides CodebaseAgent, ToolRegistry, Tool models, and default tool creation helpers.
"""

from pathlib import Path
from typing import Optional

from app.agent.agent import CodebaseAgent, DEFAULT_AGENT_SYSTEM_PROMPT
from app.agent.state import AgentResult, AgentState
from app.agent.tool_registry import Tool, ToolRegistry, ToolValidationError
from app.agent.tools import (
    SecurityError,
    create_find_symbol_tool,
    create_get_file_structure_tool,
    create_read_file_tool,
    create_search_code_tool,
    resolve_safe_path,
)
from app.llm.base import LLMProvider
from app.search.semantic_search import SemanticSearcher
from app.vector_store.qdrant_store import DEFAULT_COLLECTION_NAME, QdrantVectorStore


def create_default_tool_registry(
    searcher: SemanticSearcher,
    project_root: Optional[Path] = None,
    vector_store: Optional[QdrantVectorStore] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> ToolRegistry:
    """
    Creates and populates a ToolRegistry with the standard read-only codebase tools.
    """
    root = (project_root or Path.cwd()).resolve()
    registry = ToolRegistry()

    # 1. search_code
    search_spec = create_search_code_tool(searcher=searcher)
    registry.register(Tool(**search_spec))

    # 2. read_file
    read_spec = create_read_file_tool(project_root=root)
    registry.register(Tool(**read_spec))

    # 3. find_symbol
    symbol_spec = create_find_symbol_tool(
        vector_store=vector_store,
        collection_name=collection_name,
        project_root=root,
    )
    registry.register(Tool(**symbol_spec))

    # 4. get_file_structure
    struct_spec = create_get_file_structure_tool(project_root=root)
    registry.register(Tool(**struct_spec))

    return registry


def create_codebase_agent(
    llm: LLMProvider,
    searcher: SemanticSearcher,
    project_root: Optional[Path] = None,
    vector_store: Optional[QdrantVectorStore] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    system_prompt: Optional[str] = None,
    max_iterations: Optional[int] = None,
    max_tool_calls: Optional[int] = None,
) -> CodebaseAgent:
    """
    Factory helper to instantiate a fully configured CodebaseAgent with all standard tools.
    """
    registry = create_default_tool_registry(
        searcher=searcher,
        project_root=project_root,
        vector_store=vector_store,
        collection_name=collection_name,
    )
    return CodebaseAgent(
        llm=llm,
        tool_registry=registry,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        max_tool_calls=max_tool_calls,
    )


__all__ = [
    "CodebaseAgent",
    "AgentState",
    "AgentResult",
    "Tool",
    "ToolRegistry",
    "ToolValidationError",
    "SecurityError",
    "DEFAULT_AGENT_SYSTEM_PROMPT",
    "create_default_tool_registry",
    "create_codebase_agent",
    "resolve_safe_path",
]
