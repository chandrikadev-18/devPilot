"""
DevPilot Graph Query and Traversal Engine.

Implements caller/callee lookup, multi-depth dependency traversal with cycle
prevention, static impact analysis, and file dependency extraction.
"""

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.graph.models import EdgeType, GraphNode, NodeType, normalize_graph_path
from app.graph.store import GraphStore


class AmbiguousSymbolError(Exception):
    """Raised when a symbol name matches multiple distinct nodes and cannot be disambiguated."""
    pass


def _resolve_target_nodes(graph: GraphStore, symbol: str, allow_multiple: bool = False) -> List[GraphNode]:
    """Resolves a symbol string (node ID, symbol name, class.method, or file::symbol) to matching GraphNode(s)."""
    if not symbol or not symbol.strip():
        return []

    target = symbol.strip()

    # 1. Exact node ID match
    node = graph.get_node(target)
    if node:
        return [node]

    # 1b. Node ID with normalized path (e.g. method:app\graph\builder.py:GraphBuilder.build)
    for prefix in ("method:", "function:", "class:", "file:", "module:"):
        if target.startswith(prefix):
            rest = target[len(prefix):]
            if ":" in rest:
                path_part, sym_part = rest.rsplit(":", 1)
                norm_p = normalize_graph_path(path_part)
                candidate_id = f"{prefix}{norm_p}:{sym_part}"
                node = graph.get_node(candidate_id)
                if node:
                    return [node]
            else:
                norm_p = normalize_graph_path(rest)
                candidate_id = f"{prefix}{norm_p}"
                node = graph.get_node(candidate_id)
                if node:
                    return [node]

    # 2. File-qualified symbol formats (e.g. app/graph/builder.py::GraphBuilder.build or app/graph/builder.py:build)
    file_spec = None
    sym_spec = None
    if "::" in target:
        file_spec, sym_spec = target.split("::", 1)
    elif ":" in target and not target.startswith(("http:", "https:")):
        file_spec, sym_spec = target.rsplit(":", 1)

    if file_spec and sym_spec:
        norm_f = normalize_graph_path(file_spec.strip())
        s_target = sym_spec.strip()
        candidate_nodes = [
            n for n in graph.get_nodes()
            if n.file_path and (norm_f == n.file_path or norm_f in n.file_path or n.file_path.endswith(norm_f))
        ]
        if candidate_nodes:
            matched = []
            if "." in s_target:
                parts = s_target.split(".")
                p_cls = parts[-2]
                m_name = parts[-1]
                matched = [
                    n for n in candidate_nodes
                    if (n.node_type == NodeType.METHOD and n.name == m_name and n.metadata.get("parent_class") == p_cls)
                    or n.name == s_target
                ]
            else:
                matched = [
                    n for n in candidate_nodes
                    if n.name == s_target or n.name.lower() == s_target.lower()
                ]

            if len(matched) == 1:
                return matched
            if len(matched) > 1 and not allow_multiple:
                raise AmbiguousSymbolError(
                    f"Symbol '{symbol}' is ambiguous and matches multiple entities: {[n.id for n in matched]}"
                )
            if matched:
                return matched

    # 3. Try class.method format (e.g. GraphBuilder.build or AuthService.login)
    if "." in target:
        parts = target.split(".")
        p_cls = parts[-2]
        m_name = parts[-1]
        nodes = graph.find_nodes_by_name(m_name)
        matched = [
            n for n in nodes
            if (n.node_type == NodeType.METHOD and n.metadata.get("parent_class") == p_cls)
            or n.name == target
        ]
        if not matched:
            matched = graph.find_nodes_by_name(target)

        if len(matched) == 1:
            return matched
        if len(matched) > 1 and not allow_multiple:
            raise AmbiguousSymbolError(
                f"Symbol '{symbol}' is ambiguous and matches multiple entities: {[n.id for n in matched]}"
            )
        if matched:
            return matched

    # 4. By symbol name
    nodes = graph.find_nodes_by_name(target)
    if len(nodes) == 1:
        return nodes
    if len(nodes) > 1 and not allow_multiple:
        raise AmbiguousSymbolError(
            f"Symbol '{symbol}' is ambiguous and matches multiple entities: {[n.id for n in nodes]}"
        )
    if nodes:
        return nodes

    # 5. Partial file path match
    norm_t = normalize_graph_path(target)
    file_nodes = [
        n for n in graph.get_nodes(NodeType.FILE)
        if norm_t == n.file_path or norm_t in n.file_path or n.file_path.endswith(norm_t)
    ]
    if len(file_nodes) == 1:
        return file_nodes
    if len(file_nodes) > 1 and not allow_multiple:
        raise AmbiguousSymbolError(
            f"Symbol '{symbol}' is ambiguous and matches multiple files: {[n.id for n in file_nodes]}"
        )
    if file_nodes:
        return file_nodes

    return []


def get_callers(graph: GraphStore, symbol: str) -> List[Dict[str, Any]]:
    """
    Returns all functions and methods that directly call the given symbol.
    """
    try:
        target_nodes = _resolve_target_nodes(graph, symbol, allow_multiple=True)
    except AmbiguousSymbolError:
        target_nodes = []

    if not target_nodes:
        return []

    callers_list: List[Dict[str, Any]] = []
    seen_callers: Set[str] = set()

    for t_node in target_nodes:
        incoming_edges = graph.get_incoming_edges(t_node.id, edge_type=EdgeType.CALLS)
        for edge in incoming_edges:
            caller_node = graph.get_node(edge.source_id)
            if caller_node and caller_node.id not in seen_callers:
                seen_callers.add(caller_node.id)
                callers_list.append({
                    "id": caller_node.id,
                    "name": caller_node.name,
                    "node_type": caller_node.node_type.value,
                    "file_path": caller_node.file_path,
                    "start_line": caller_node.start_line,
                    "end_line": caller_node.end_line,
                    "call_line": edge.line_number,
                    "target_symbol": t_node.name,
                })

    return callers_list


def get_callees(graph: GraphStore, symbol: str) -> List[Dict[str, Any]]:
    """
    Returns all functions and methods called by the given symbol.
    """
    try:
        source_nodes = _resolve_target_nodes(graph, symbol, allow_multiple=True)
    except AmbiguousSymbolError:
        source_nodes = []

    if not source_nodes:
        return []

    callees_list: List[Dict[str, Any]] = []
    seen_callees: Set[str] = set()

    for s_node in source_nodes:
        outgoing_edges = graph.get_outgoing_edges(s_node.id, edge_type=EdgeType.CALLS)
        for edge in outgoing_edges:
            callee_node = graph.get_node(edge.target_id)
            if callee_node and callee_node.id not in seen_callees:
                seen_callees.add(callee_node.id)
                callees_list.append({
                    "id": callee_node.id,
                    "name": callee_node.name,
                    "node_type": callee_node.node_type.value,
                    "file_path": callee_node.file_path,
                    "start_line": callee_node.start_line,
                    "end_line": callee_node.end_line,
                    "call_line": edge.line_number,
                    "caller_symbol": s_node.name,
                })

    return callees_list


def get_dependencies(
    graph: GraphStore,
    symbol: str,
    depth: int = 1,
) -> Dict[str, Any]:
    """
    Traverses downstream CALLS dependencies up to the specified depth with cycle prevention.
    """
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    try:
        start_nodes = _resolve_target_nodes(graph, symbol, allow_multiple=True)
    except AmbiguousSymbolError as e:
        return {
            "symbol": symbol,
            "depth": depth,
            "error": str(e),
            "total_dependencies": 0,
            "dependencies": [],
        }

    if not start_nodes:
        return {
            "symbol": symbol,
            "depth": depth,
            "total_dependencies": 0,
            "dependencies": [],
        }

    max_depth = depth
    dependencies: List[Dict[str, Any]] = []
    visited: Set[str] = {n.id for n in start_nodes}

    # Queue items: (current_node, current_depth, call_path)
    queue = deque([(n, 0, [n.name]) for n in start_nodes])

    while queue:
        curr_node, curr_d, path = queue.popleft()
        if curr_d >= max_depth:
            continue

        outgoing = graph.get_outgoing_edges(curr_node.id, edge_type=EdgeType.CALLS)
        for edge in outgoing:
            target_n = graph.get_node(edge.target_id)
            if not target_n:
                continue

            next_depth = curr_d + 1
            next_path = path + [target_n.name]

            dep_entry = {
                "id": target_n.id,
                "name": target_n.name,
                "node_type": target_n.node_type.value,
                "file_path": target_n.file_path,
                "start_line": target_n.start_line,
                "end_line": target_n.end_line,
                "call_line": edge.line_number,
                "depth": next_depth,
                "caller": curr_node.name,
                "call_path": " -> ".join(next_path),
            }
            dependencies.append(dep_entry)

            if target_n.id not in visited:
                visited.add(target_n.id)
                queue.append((target_n, next_depth, next_path))

    return {
        "symbol": symbol,
        "depth": max_depth,
        "total_dependencies": len(dependencies),
        "dependencies": dependencies,
    }


def get_dependents(
    graph: GraphStore,
    symbol: str,
    depth: int = 1,
) -> Dict[str, Any]:
    """
    Traverses reverse/upstream CALLS dependencies (who calls this) up to the specified depth.
    """
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    try:
        start_nodes = _resolve_target_nodes(graph, symbol, allow_multiple=True)
    except AmbiguousSymbolError as e:
        return {
            "symbol": symbol,
            "depth": depth,
            "error": str(e),
            "total_dependents": 0,
            "dependents": [],
        }

    if not start_nodes:
        return {
            "symbol": symbol,
            "depth": depth,
            "total_dependents": 0,
            "dependents": [],
        }

    max_depth = depth
    dependents: List[Dict[str, Any]] = []
    visited: Set[str] = {n.id for n in start_nodes}

    # Queue items: (current_node, current_depth, call_path)
    queue = deque([(n, 0, [n.name]) for n in start_nodes])

    while queue:
        curr_node, curr_d, path = queue.popleft()
        if curr_d >= max_depth:
            continue

        incoming = graph.get_incoming_edges(curr_node.id, edge_type=EdgeType.CALLS)
        for edge in incoming:
            caller_n = graph.get_node(edge.source_id)
            if not caller_n:
                continue

            next_depth = curr_d + 1
            next_path = [caller_n.name] + path

            dep_entry = {
                "id": caller_n.id,
                "name": caller_n.name,
                "node_type": caller_n.node_type.value,
                "file_path": caller_n.file_path,
                "start_line": caller_n.start_line,
                "end_line": caller_n.end_line,
                "call_line": edge.line_number,
                "depth": next_depth,
                "calls_target": curr_node.name,
                "dependent_path": " -> ".join(next_path),
            }
            dependents.append(dep_entry)

            if caller_n.id not in visited:
                visited.add(caller_n.id)
                queue.append((caller_n, next_depth, next_path))

    return {
        "symbol": symbol,
        "depth": max_depth,
        "total_dependents": len(dependents),
        "dependents": dependents,
    }


def get_impact(
    graph: GraphStore,
    symbol: str,
    depth: int = 2,
) -> Dict[str, Any]:
    """
    Performs static dependency impact analysis: discovers direct and indirect upstream callers.
    """
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    try:
        start_nodes = _resolve_target_nodes(graph, symbol, allow_multiple=True)
    except AmbiguousSymbolError as e:
        return {
            "symbol": symbol,
            "depth": depth,
            "error": str(e),
            "total_impacted": 0,
            "direct_callers": [],
            "indirect_callers": [],
            "direct_dependents": [],
            "indirect_dependents": [],
            "impacted_files": [],
        }

    if not start_nodes:
        return {
            "symbol": symbol,
            "depth": depth,
            "total_impacted": 0,
            "direct_callers": [],
            "indirect_callers": [],
            "direct_dependents": [],
            "indirect_dependents": [],
            "impacted_files": [],
        }

    max_depth = depth
    direct_callers: List[Dict[str, Any]] = []
    indirect_callers: List[Dict[str, Any]] = []
    impacted_files: Set[str] = set()
    visited: Set[str] = {n.id for n in start_nodes}
    seen_callers: Set[str] = set()

    # Queue items: (current_node, current_depth)
    queue = deque([(n, 0) for n in start_nodes])

    while queue:
        curr_node, curr_d = queue.popleft()
        if curr_d >= max_depth:
            continue

        incoming = graph.get_incoming_edges(curr_node.id, edge_type=EdgeType.CALLS)
        for edge in incoming:
            caller_n = graph.get_node(edge.source_id)
            if not caller_n:
                continue

            next_depth = curr_d + 1
            if caller_n.file_path:
                impacted_files.add(caller_n.file_path)

            item = {
                "id": caller_n.id,
                "name": caller_n.name,
                "node_type": caller_n.node_type.value,
                "file_path": caller_n.file_path,
                "start_line": caller_n.start_line,
                "end_line": caller_n.end_line,
                "call_line": edge.line_number,
                "calls_target": curr_node.name,
                "depth": next_depth,
            }

            if caller_n.id not in seen_callers:
                seen_callers.add(caller_n.id)
                if next_depth == 1:
                    direct_callers.append(item)
                else:
                    indirect_callers.append(item)

            if caller_n.id not in visited:
                visited.add(caller_n.id)
                queue.append((caller_n, next_depth))

    return {
        "symbol": symbol,
        "depth": max_depth,
        "analysis_type": "STATIC DEPENDENCY IMPACT",
        "total_impacted": len(direct_callers) + len(indirect_callers),
        "direct_callers": direct_callers,
        "indirect_callers": indirect_callers,
        "direct_dependents": direct_callers,
        "indirect_dependents": indirect_callers,
        "impacted_files": sorted(impacted_files),
    }


def get_file_dependencies(
    graph: GraphStore,
    file_path: str,
) -> Dict[str, Any]:
    """
    Extracts module and file-level import relationships for a file.
    """
    norm_path = normalize_graph_path(file_path)
    file_node_id = f"file:{norm_path}"
    file_node = graph.get_node(file_node_id)

    # Fallback to suffix search if not found
    if not file_node:
        candidates = [n for n in graph.get_nodes(NodeType.FILE) if norm_path in n.file_path]
        if candidates:
            file_node = candidates[0]

    if not file_node:
        return {
            "file_path": file_path,
            "error": f"File '{file_path}' is not indexed in the dependency graph.",
            "imports_files": [],
            "imports_modules": [],
            "imported_by": [],
            "defined_symbols": [],
        }

    # Outgoing IMPORTS
    imports_files: List[str] = []
    imports_modules: List[str] = []
    for edge in graph.get_outgoing_edges(file_node.id, edge_type=EdgeType.IMPORTS):
        target_n = graph.get_node(edge.target_id)
        if target_n:
            if target_n.node_type == NodeType.FILE:
                imports_files.append(target_n.file_path)
            elif target_n.node_type == NodeType.MODULE:
                imports_modules.append(target_n.name)

    # Incoming IMPORTS (who imports this file)
    imported_by: List[str] = []
    for edge in graph.get_incoming_edges(file_node.id, edge_type=EdgeType.IMPORTS):
        src_n = graph.get_node(edge.source_id)
        if src_n and src_n.node_type == NodeType.FILE:
            imported_by.append(src_n.file_path)

    # Defined symbols in this file
    symbols: List[Dict[str, Any]] = []
    for node in graph.get_nodes_in_file(file_node.file_path):
        if node.node_type in (NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD):
            symbols.append({
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type.value,
                "start_line": node.start_line,
                "end_line": node.end_line,
            })

    return {
        "file_path": file_node.file_path,
        "imports_files": sorted(set(imports_files)),
        "imports_modules": sorted(set(imports_modules)),
        "imported_by": sorted(set(imported_by)),
        "defined_symbols": symbols,
    }
