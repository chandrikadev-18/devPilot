"""
DevPilot Read-Only Codebase Tools.

Implements search_code, read_file, find_symbol, and get_file_structure
with strict sandbox and security boundaries.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_max_tool_result_characters
from app.parser.python_parser import PythonParser
from app.search.semantic_search import SemanticSearcher
from app.vector_store.qdrant_store import DEFAULT_COLLECTION_NAME, QdrantVectorStore


class SecurityError(Exception):
    """Raised when a tool operation violates project boundaries or security rules."""
    pass


def resolve_safe_path(file_path: str, project_root: Optional[Path] = None) -> Path:
    """
    Safely resolves a file path within the project directory.
    Rejects directory traversal, paths outside project root, .env, and .git files.
    """
    if not file_path or not file_path.strip():
        raise SecurityError("File path cannot be empty.")

    root = (project_root or Path.cwd()).resolve()

    # Reject obvious traversal attempts
    raw_str = file_path.strip().replace("\\", "/")
    if raw_str.startswith("../") or "/../" in raw_str or raw_str == "..":
        raise SecurityError(f"Directory traversal is forbidden: '{file_path}'")

    # Reject .env access
    normalized_lower = Path(raw_str).as_posix().lower()
    parts = [p.lower() for p in Path(raw_str).parts]
    if any(p.startswith(".env") for p in parts) or normalized_lower.endswith(".env"):
        raise SecurityError(f"Access to environment files is forbidden: '{file_path}'")

    # Reject .git access
    if any(p == ".git" for p in parts):
        raise SecurityError(f"Access to internal .git directory is forbidden: '{file_path}'")

    # Resolve target
    if Path(raw_str).is_absolute():
        target = Path(raw_str).resolve()
    else:
        target = (root / raw_str).resolve()

    # Ensure target is strictly inside project root
    try:
        target.relative_to(root)
    except ValueError:
        raise SecurityError(f"Access denied: '{file_path}' resolves outside project root '{root}'")

    return target


def create_search_code_tool(
    searcher: SemanticSearcher,
) -> Dict[str, Any]:
    """Factory for the search_code tool."""

    def search_code(query: str, top_k: int = 5) -> Dict[str, Any]:
        """Searches the indexed codebase for semantic matches."""
        results = searcher.search(query=query, top_k=top_k)
        if not results:
            return {
                "data": f"No relevant code found matching query: '{query}'",
                "sources": [],
            }

        data_list = []
        sources = []
        for r in results:
            item = {
                "chunk_id": r.chunk_id,
                "file_path": r.file_path,
                "symbol_name": r.symbol_name,
                "symbol_type": r.symbol_type,
                "parent_symbol": r.parent_symbol,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": round(r.score, 4),
                "code": r.code,
            }
            data_list.append(item)
            sources.append({
                "chunk_id": r.chunk_id,
                "file_path": r.file_path,
                "symbol_name": r.symbol_name,
                "symbol_type": r.symbol_type,
                "parent_symbol": r.parent_symbol,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": round(r.score, 4),
            })

        return {
            "data": data_list,
            "sources": sources,
        }

    return {
        "name": "search_code",
        "description": "Searches indexed codebase chunks using natural language query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "top_k": {"type": "integer", "minimum": 1, "description": "Max results to return (default: 5)"},
            },
            "required": ["query"],
        },
        "func": search_code,
        "safety_level": "read_only",
    }


def create_read_file_tool(
    project_root: Optional[Path] = None,
    max_characters: Optional[int] = None,
) -> Dict[str, Any]:
    """Factory for the read_file tool."""
    root = (project_root or Path.cwd()).resolve()
    char_limit = max_characters or get_max_tool_result_characters()

    def read_file(file_path: str) -> Dict[str, Any]:
        """Reads a file safely within project boundaries."""
        safe_path = resolve_safe_path(file_path, project_root=root)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: '{file_path}'")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: '{file_path}'")

        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            raise IOError(f"Could not read file '{file_path}': {e}") from e

        rel_path = safe_path.relative_to(root).as_posix()
        line_count = len(content.splitlines())

        truncated = False
        if len(content) > char_limit:
            content = content[:char_limit].rstrip() + "\n\n[File truncated due to size limit]"
            truncated = True

        sources = [{
            "file_path": rel_path,
            "symbol_name": safe_path.name,
            "symbol_type": "file",
            "start_line": 1,
            "end_line": line_count,
        }]

        return {
            "data": {
                "file_path": rel_path,
                "lines": line_count,
                "truncated": truncated,
                "content": content,
            },
            "sources": sources,
        }

    return {
        "name": "read_file",
        "description": "Reads the text contents of a file in the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the project file to read"},
            },
            "required": ["file_path"],
        },
        "func": read_file,
        "safety_level": "read_only",
    }


def create_find_symbol_tool(
    vector_store: Optional[QdrantVectorStore] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for find_symbol tool."""
    root = (project_root or Path.cwd()).resolve()

    def find_symbol(symbol_name: str) -> Dict[str, Any]:
        """Locates symbol definitions in indexed points or through AST parsing."""
        if not symbol_name or not symbol_name.strip():
            raise ValueError("symbol_name cannot be empty.")

        target_name = symbol_name.strip().lower()
        matches = []
        sources = []

        # 1. Try querying Qdrant payload if vector_store is available
        if vector_store and vector_store.collection_exists(collection_name):
            try:
                # Scroll points to locate matching symbol_name
                scroll_res = vector_store.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    with_payload=True,
                    with_vectors=False,
                )
                points = scroll_res[0] if isinstance(scroll_res, tuple) else scroll_res
                for pt in points:
                    payload = pt.payload or {}
                    s_name = payload.get("symbol_name", "")
                    p_symbol = payload.get("parent_symbol", "")
                    if target_name in s_name.lower() or (p_symbol and target_name in p_symbol.lower()):
                        item = {
                            "chunk_id": payload.get("chunk_id", str(pt.id)),
                            "file_path": payload.get("file_path", ""),
                            "symbol_name": s_name,
                            "symbol_type": payload.get("symbol_type", ""),
                            "parent_symbol": payload.get("parent_symbol"),
                            "start_line": payload.get("start_line", 0),
                            "end_line": payload.get("end_line", 0),
                            "code": payload.get("code", ""),
                        }
                        matches.append(item)
                        sources.append({
                            "chunk_id": item["chunk_id"],
                            "file_path": item["file_path"],
                            "symbol_name": item["symbol_name"],
                            "symbol_type": item["symbol_type"],
                            "parent_symbol": item["parent_symbol"],
                            "start_line": item["start_line"],
                            "end_line": item["end_line"],
                        })
            except Exception:
                pass

        # 2. Fallback / Direct AST inspection across project python files if no indexed matches
        if not matches:
            parser = PythonParser()
            for py_file in root.rglob("*.py"):
                # Avoid hidden/ignored folders
                parts = [p.lower() for p in py_file.parts]
                if any(p.startswith(".") or p in ("venv", "node_modules", "__pycache__") for p in parts):
                    continue
                try:
                    rel_p = py_file.relative_to(root).as_posix()
                    file_info = parser.parse_file(str(py_file))
                    if "error" in file_info:
                        continue

                    # Check classes
                    for cls in file_info.get("classes", []):
                        if target_name == cls.get("name", "").lower():
                            matches.append({
                                "file_path": rel_p,
                                "symbol_name": cls["name"],
                                "symbol_type": "class",
                                "parent_symbol": None,
                                "start_line": cls.get("start_line", 0),
                                "end_line": cls.get("end_line", 0),
                                "code": cls.get("code", ""),
                            })
                            sources.append({
                                "file_path": rel_p,
                                "symbol_name": cls["name"],
                                "symbol_type": "class",
                                "parent_symbol": None,
                                "start_line": cls.get("start_line", 0),
                                "end_line": cls.get("end_line", 0),
                            })

                    # Check functions
                    for fn in file_info.get("functions", []):
                        if target_name == fn.get("name", "").lower():
                            matches.append({
                                "file_path": rel_p,
                                "symbol_name": fn["name"],
                                "symbol_type": "function",
                                "parent_symbol": None,
                                "start_line": fn.get("start_line", 0),
                                "end_line": fn.get("end_line", 0),
                                "code": fn.get("code", ""),
                            })
                            sources.append({
                                "file_path": rel_p,
                                "symbol_name": fn["name"],
                                "symbol_type": "function",
                                "parent_symbol": None,
                                "start_line": fn.get("start_line", 0),
                                "end_line": fn.get("end_line", 0),
                            })

                    # Check methods
                    for m in file_info.get("methods", []):
                        if target_name == m.get("name", "").lower():
                            matches.append({
                                "file_path": rel_p,
                                "symbol_name": m["name"],
                                "symbol_type": "method",
                                "parent_symbol": m.get("parent_class"),
                                "start_line": m.get("start_line", 0),
                                "end_line": m.get("end_line", 0),
                                "code": m.get("code", ""),
                            })
                            sources.append({
                                "file_path": rel_p,
                                "symbol_name": m["name"],
                                "symbol_type": "method",
                                "parent_symbol": m.get("parent_class"),
                                "start_line": m.get("start_line", 0),
                                "end_line": m.get("end_line", 0),
                            })
                except Exception:
                    continue

        if not matches:
            return {
                "data": f"Symbol '{symbol_name}' was not found in the codebase.",
                "sources": [],
            }

        return {
            "data": matches,
            "sources": sources,
        }

    return {
        "name": "find_symbol",
        "description": "Locates symbol definitions (functions, classes, methods) across the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Name of the function, class, or method to find"},
            },
            "required": ["symbol_name"],
        },
        "func": find_symbol,
        "safety_level": "read_only",
    }


def create_get_file_structure_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_file_structure tool."""
    root = (project_root or Path.cwd()).resolve()
    parser = PythonParser()

    def get_file_structure(file_path: str) -> Dict[str, Any]:
        """Parses AST metadata from a file without executing code."""
        safe_path = resolve_safe_path(file_path, project_root=root)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: '{file_path}'")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: '{file_path}'")

        if safe_path.suffix != ".py":
            return {
                "data": f"File structure AST parsing is currently supported for Python (.py) files, got '{safe_path.suffix}'",
                "sources": [],
            }

        res = parser.parse_file(str(safe_path))
        if "error" in res:
            return {
                "data": f"Failed to parse file '{file_path}': {res['error']}",
                "sources": [],
            }

        rel_p = safe_path.relative_to(root).as_posix()
        classes = [{"name": c["name"], "start_line": c["start_line"], "end_line": c["end_line"]} for c in res.get("classes", [])]
        functions = [{"name": f["name"], "start_line": f["start_line"], "end_line": f["end_line"]} for f in res.get("functions", [])]
        methods = [{"name": m["name"], "class": m.get("parent_class"), "start_line": m["start_line"], "end_line": m["end_line"]} for m in res.get("methods", [])]
        imports = [imp.get("name", "") for imp in res.get("imports", [])]

        sources = [{
            "file_path": rel_p,
            "symbol_name": safe_path.name,
            "symbol_type": "file_structure",
            "start_line": 1,
            "end_line": len(safe_path.read_text(encoding="utf-8", errors="replace").splitlines()),
        }]

        return {
            "data": {
                "file_path": rel_p,
                "imports": imports,
                "classes": classes,
                "functions": functions,
                "methods": methods,
            },
            "sources": sources,
        }

    return {
        "name": "get_file_structure",
        "description": "Extracts structural AST overview (classes, functions, methods, imports) of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the Python file to inspect"},
            },
            "required": ["file_path"],
        },
        "func": get_file_structure,
        "safety_level": "read_only",
    }
