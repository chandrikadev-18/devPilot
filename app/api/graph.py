from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.graph.builder import GraphBuilder
from app.graph.models import EdgeType, NodeType
from app.graph.queries import (
    AmbiguousSymbolError,
    get_callees,
    get_callers,
    get_dependencies,
    get_dependents,
    get_file_dependencies,
    get_impact,
)
from app.graph.store import GraphStore
from app.schemas.graph import (
    CalleesResponse,
    CallersResponse,
    DependenciesResponse,
    DependentsResponse,
    GraphInfoResponse,
    ImpactResponse,
)

router = APIRouter(prefix="/graph", tags=["Dependency Graph"])


def _get_graph(project_dir: str = ".", graph_path: Optional[str] = None) -> GraphStore:
    """Helper to resolve or build the dependency graph for a directory."""
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project directory does not exist: '{project_dir}'",
        )

    target_path = Path(graph_path).resolve() if graph_path else root / "data" / "graph.json"
    if target_path.is_file():
        try:
            return GraphStore.load(target_path)
        except Exception:
            pass

    try:
        return GraphBuilder().build(root)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build codebase dependency graph: {str(e)}",
        )


@router.get(
    "/info",
    response_model=GraphInfoResponse,
    summary="Get Dependency Graph Statistics",
    description="Returns aggregate node and edge counts of the codebase dependency graph.",
)
def get_graph_info(
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
) -> GraphInfoResponse:
    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    nodes = graph.get_nodes()
    edges = graph.get_edges()

    return GraphInfoResponse(
        total_nodes=len(nodes),
        files=len([n for n in nodes if n.node_type == NodeType.FILE]),
        classes=len([n for n in nodes if n.node_type == NodeType.CLASS]),
        functions=len([n for n in nodes if n.node_type == NodeType.FUNCTION]),
        methods=len([n for n in nodes if n.node_type == NodeType.METHOD]),
        modules=len([n for n in nodes if n.node_type == NodeType.MODULE]),
        total_edges=len(edges),
        calls=len([e for e in edges if e.edge_type == EdgeType.CALLS]),
        imports=len([e for e in edges if e.edge_type == EdgeType.IMPORTS]),
        contains=len([e for e in edges if e.edge_type == EdgeType.CONTAINS]),
        defines=len([e for e in edges if e.edge_type == EdgeType.DEFINES]),
        belongs_to=len([e for e in edges if e.edge_type == EdgeType.BELONGS_TO]),
    )


@router.get(
    "/callers",
    response_model=CallersResponse,
    summary="Get Callers of a Symbol",
    description="Finds all functions and methods that directly call the specified symbol.",
)
def get_symbol_callers(
    symbol: str = Query(..., description="Target symbol name or identifier (e.g. 'build' or 'GraphBuilder.build')"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
    strict: bool = Query(False, description="If true, raises 404 when no callers or target symbol are found"),
) -> CallersResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")

    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    callers = get_callers(graph, symbol=symbol.strip())

    if strict and not callers:
        raise HTTPException(status_code=404, detail=f"No callers found for symbol '{symbol}'.")

    return CallersResponse(
        symbol=symbol,
        total_callers=len(callers),
        callers=callers,
    )


@router.get(
    "/callees",
    response_model=CalleesResponse,
    summary="Get Callees of a Symbol",
    description="Finds all functions and methods called by the specified symbol.",
)
def get_symbol_callees(
    symbol: str = Query(..., description="Source symbol name or identifier (e.g. 'build' or 'GraphBuilder.build')"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
    strict: bool = Query(False, description="If true, raises 404 when no callees are found"),
) -> CalleesResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")

    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    callees = get_callees(graph, symbol=symbol.strip())

    if strict and not callees:
        raise HTTPException(status_code=404, detail=f"No callees found for symbol '{symbol}'.")

    return CalleesResponse(
        symbol=symbol,
        total_callees=len(callees),
        callees=callees,
    )


@router.get(
    "/dependencies",
    response_model=DependenciesResponse,
    summary="Get Downstream Dependencies",
    description="Traverses downstream call dependencies for a symbol up to the specified depth.",
)
def get_symbol_dependencies(
    symbol: str = Query(..., description="Target symbol name or identifier"),
    depth: int = Query(1, description="Depth of traversal (1-10)"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
) -> DependenciesResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")
    if depth < 1 or depth > 10:
        raise HTTPException(status_code=400, detail=f"Invalid depth '{depth}'. Depth must be between 1 and 10.")

    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    try:
        dep_result = get_dependencies(graph, symbol=symbol.strip(), depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying dependencies: {str(e)}")

    return DependenciesResponse(
        symbol=dep_result["symbol"],
        depth=dep_result["depth"],
        total_dependencies=dep_result["total_dependencies"],
        dependencies=dep_result.get("dependencies", []),
    )


@router.get(
    "/dependents",
    response_model=DependentsResponse,
    summary="Get Upstream Dependents",
    description="Traverses upstream reverse call dependencies (who calls this) up to the specified depth.",
)
def get_symbol_dependents(
    symbol: str = Query(..., description="Target symbol name or identifier"),
    depth: int = Query(1, description="Depth of traversal (1-10)"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
) -> DependentsResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")
    if depth < 1 or depth > 10:
        raise HTTPException(status_code=400, detail=f"Invalid depth '{depth}'. Depth must be between 1 and 10.")

    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    try:
        dep_result = get_dependents(graph, symbol=symbol.strip(), depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying dependents: {str(e)}")

    return DependentsResponse(
        symbol=dep_result["symbol"],
        depth=dep_result["depth"],
        total_dependents=dep_result["total_dependents"],
        dependents=dep_result.get("dependents", []),
    )


@router.get(
    "/impact",
    response_model=ImpactResponse,
    summary="Perform Static Dependency Impact Analysis",
    description="Discovers all direct and indirect upstream callers and affected files up to the specified depth.",
)
def get_symbol_impact(
    symbol: str = Query(..., description="Target symbol name or identifier to analyze impact for"),
    depth: int = Query(2, description="Depth of impact traversal (1-10)"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
) -> ImpactResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")
    if depth < 1 or depth > 10:
        raise HTTPException(status_code=400, detail=f"Invalid depth '{depth}'. Depth must be between 1 and 10.")

    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    try:
        impact_result = get_impact(graph, symbol=symbol.strip(), depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying impact: {str(e)}")

    return ImpactResponse(
        symbol=impact_result["symbol"],
        depth=impact_result["depth"],
        analysis_type=impact_result.get("analysis_type", "STATIC DEPENDENCY IMPACT"),
        total_impacted=impact_result["total_impacted"],
        direct_callers=impact_result.get("direct_callers", []),
        indirect_callers=impact_result.get("indirect_callers", []),
        direct_dependents=impact_result.get("direct_dependents", []),
        indirect_dependents=impact_result.get("indirect_dependents", []),
        impacted_files=impact_result.get("impacted_files", []),
    )


@router.get(
    "/file-dependencies",
    summary="Get File Dependencies",
    description="Extracts module and file-level import relationships for a file.",
)
def get_file_dependencies_endpoint(
    file_path: str = Query(..., description="Target file path"),
    project_dir: str = Query(".", description="Target codebase directory"),
    graph_path: Optional[str] = Query(None, description="Optional custom graph JSON file path"),
):
    graph = _get_graph(project_dir=project_dir, graph_path=graph_path)
    return get_file_dependencies(graph, file_path=file_path)


@router.post(
    "/build",
    response_model=GraphInfoResponse,
    summary="Build Graph",
    description="Builds or rebuilds the dependency graph for a directory.",
)
def build_graph_endpoint(
    directory: str = Query(".", description="Target directory"),
) -> GraphInfoResponse:
    root = Path(directory).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {directory}")
    try:
        graph = GraphBuilder().build(root)
        try:
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            graph.save(data_dir / "graph.json")
        except Exception:
            pass
        nodes = graph.get_nodes()
        edges = graph.get_edges()
        return GraphInfoResponse(
            total_nodes=len(nodes),
            files=len([n for n in nodes if n.node_type == NodeType.FILE]),
            classes=len([n for n in nodes if n.node_type == NodeType.CLASS]),
            functions=len([n for n in nodes if n.node_type == NodeType.FUNCTION]),
            methods=len([n for n in nodes if n.node_type == NodeType.METHOD]),
            modules=len([n for n in nodes if n.node_type == NodeType.MODULE]),
            total_edges=len(edges),
            calls=len([e for e in edges if e.edge_type == EdgeType.CALLS]),
            imports=len([e for e in edges if e.edge_type == EdgeType.IMPORTS]),
            contains=len([e for e in edges if e.edge_type == EdgeType.CONTAINS]),
            defines=len([e for e in edges if e.edge_type == EdgeType.DEFINES]),
            belongs_to=len([e for e in edges if e.edge_type == EdgeType.BELONGS_TO]),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build graph: {str(e)}")

