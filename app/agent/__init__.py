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
    create_get_callees_tool,
    create_get_callers_tool,
    create_get_commit_tool,
    create_get_dependencies_tool,
    create_get_dependents_tool,
    create_get_file_blame_tool,
    create_get_file_dependencies_tool,
    create_get_file_history_tool,
    create_get_file_structure_tool,
    create_get_impact_tool,
    create_get_last_commit_tool,
    create_get_recent_commits_tool,
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
    Creates and populates a ToolRegistry with the standard read-only codebase, Git, and Graph tools.
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

    # 5. get_file_history (v0.9)
    history_spec = create_get_file_history_tool(project_root=root)
    registry.register(Tool(**history_spec))

    # 6. get_recent_commits (v0.9)
    recent_spec = create_get_recent_commits_tool(project_root=root)
    registry.register(Tool(**recent_spec))

    # 7. get_last_commit (v0.9)
    last_commit_spec = create_get_last_commit_tool(project_root=root)
    registry.register(Tool(**last_commit_spec))

    # 8. get_commit (v0.9)
    commit_spec = create_get_commit_tool(project_root=root)
    registry.register(Tool(**commit_spec))

    # 9. get_file_blame (v0.9)
    blame_spec = create_get_file_blame_tool(project_root=root)
    registry.register(Tool(**blame_spec))

    # 10. get_callers (v1.0)
    callers_spec = create_get_callers_tool(project_root=root)
    registry.register(Tool(**callers_spec))

    # 11. get_callees (v1.0)
    callees_spec = create_get_callees_tool(project_root=root)
    registry.register(Tool(**callees_spec))

    # 12. get_dependencies (v1.0)
    dep_spec = create_get_dependencies_tool(project_root=root)
    registry.register(Tool(**dep_spec))

    # 13. get_dependents (v1.0)
    dependents_spec = create_get_dependents_tool(project_root=root)
    registry.register(Tool(**dependents_spec))

    # 14. get_impact (v1.0)
    impact_spec = create_get_impact_tool(project_root=root)
    registry.register(Tool(**impact_spec))

    # 15. get_file_dependencies (v1.0)
    file_dep_spec = create_get_file_dependencies_tool(project_root=root)
    registry.register(Tool(**file_dep_spec))

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
    "create_get_file_history_tool",
    "create_get_recent_commits_tool",
    "create_get_last_commit_tool",
    "create_get_commit_tool",
    "create_get_file_blame_tool",
    "create_get_callers_tool",
    "create_get_callees_tool",
    "create_get_dependencies_tool",
    "create_get_dependents_tool",
    "create_get_impact_tool",
    "create_get_file_dependencies_tool",
]
