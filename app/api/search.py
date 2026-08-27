from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.agent.tools import create_find_symbol_tool
from app.schemas.search import SymbolMatchItem, SymbolSearchResponse

router = APIRouter(prefix="/search", tags=["Symbol Search"])


@router.get(
    "/symbol",
    response_model=SymbolSearchResponse,
    summary="Search Symbols in Codebase",
    description="Locates exact symbol definitions (classes, functions, methods) via Graph, AST, and vector index.",
)
def search_symbol(
    query: str = Query(..., min_length=1, description="Symbol name or qualified identifier to search for (e.g. 'GraphBuilder.build')"),
    project_dir: str = Query(".", description="Target codebase directory"),
    strict: bool = Query(False, description="If true, raises 404 when the symbol is not found"),
) -> SymbolSearchResponse:
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")

    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    tool_spec = create_find_symbol_tool(project_root=root)
    find_symbol_func = tool_spec["func"]

    try:
        res = find_symbol_func(query.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during symbol search: {str(e)}")

    data = res.get("data", [])
    if isinstance(data, str):
        # Symbol was not found
        if strict:
            raise HTTPException(status_code=404, detail=data)
        return SymbolSearchResponse(
            query=query,
            total_matches=0,
            matches=[],
        )

    matches = []
    for item in data:
        matches.append(
            SymbolMatchItem(
                file_path=item.get("file_path", ""),
                symbol_name=item.get("symbol_name", ""),
                symbol_type=item.get("symbol_type"),
                parent_symbol=item.get("parent_symbol"),
                start_line=item.get("start_line"),
                end_line=item.get("end_line"),
                code=item.get("code"),
                chunk_id=item.get("chunk_id"),
            )
        )

    if strict and not matches:
        raise HTTPException(status_code=404, detail=f"Symbol '{query}' not found in codebase.")

    return SymbolSearchResponse(
        query=query,
        total_matches=len(matches),
        matches=matches,
    )
