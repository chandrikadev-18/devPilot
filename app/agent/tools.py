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

    def read_file(
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Reads a file safely within project boundaries, optionally slicing specific lines."""
        safe_path = resolve_safe_path(file_path, project_root=root)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: '{file_path}'")
        if safe_path.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: '{file_path}'")

        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()
        except Exception as e:
            raise IOError(f"Could not read file '{file_path}': {e}") from e

        rel_path = safe_path.relative_to(root).as_posix()
        lines = raw_content.splitlines()
        total_lines = len(lines)

        s_line = 1
        e_line = total_lines

        if start_line is not None or end_line is not None:
            s_line = max(1, start_line) if start_line is not None else 1
            e_line = min(total_lines, end_line) if end_line is not None else total_lines
            if s_line > e_line:
                s_line = e_line
            sliced_lines = lines[s_line - 1 : e_line]
            content = "\n".join(sliced_lines)
        else:
            content = raw_content

        truncated = False
        if len(content) > char_limit:
            content = content[:char_limit].rstrip() + "\n\n[File truncated due to size limit]"
            truncated = True

        sources = [{
            "file_path": rel_path,
            "symbol_name": safe_path.name,
            "symbol_type": "file",
            "start_line": s_line,
            "end_line": e_line,
        }]

        return {
            "data": {
                "file_path": rel_path,
                "lines": total_lines,
                "start_line": s_line,
                "end_line": e_line,
                "truncated": truncated,
                "content": content,
            },
            "sources": sources,
        }

    return {
        "name": "read_file",
        "description": "Reads text contents or specific line ranges of a file in the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the project file to read"},
                "start_line": {"type": "integer", "minimum": 1, "description": "Optional starting line number (1-indexed)"},
                "end_line": {"type": "integer", "minimum": 1, "description": "Optional ending line number (1-indexed)"},
            },
            "required": ["file_path"],
        },
        "func": read_file,
        "safety_level": "read_only",
    }


def create_find_symbol_tool(
    graph: Optional[Any] = None,
    vector_store: Optional[QdrantVectorStore] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for find_symbol tool."""
    root = (project_root or Path.cwd()).resolve()

    def find_symbol(symbol_name: str) -> Dict[str, Any]:
        """Locates exact symbol definitions (functions, classes, methods) via graph, AST, and index."""
        if not symbol_name or not symbol_name.strip():
            raise ValueError("symbol_name cannot be empty.")

        target_name = symbol_name.strip().lower()
        parts = [p for p in target_name.split(".") if p]
        leaf_name = parts[-1] if parts else target_name
        qualifiers = parts[:-1]

        seen_keys = set()
        exact_matches = []
        sources = []

        def get_code_snippet(rel_p: str, start_line: int, end_line: int) -> str:
            if not rel_p or start_line <= 0:
                return ""
            try:
                safe = resolve_safe_path(rel_p, project_root=root)
                if safe.is_file():
                    lines = safe.read_text(encoding="utf-8", errors="replace").splitlines()
                    s_idx = max(0, start_line - 1)
                    e_idx = min(len(lines), end_line) if end_line > 0 else len(lines)
                    return "\n".join(lines[s_idx:e_idx])
            except Exception:
                pass
            return ""

        def matches_qualifiers(file_path: str, parent_symbol: Optional[str]) -> bool:
            if not qualifiers:
                return True
            f_lower = file_path.lower().replace("\\", "/")
            p_lower = (parent_symbol or "").lower()
            for q in qualifiers:
                if q in f_lower or q in p_lower:
                    return True
            return False

        def add_match(item: Dict[str, Any], src: Dict[str, Any]):
            key = (item.get("file_path"), item.get("symbol_name"), item.get("start_line"))
            if key not in seen_keys:
                seen_keys.add(key)
                if not item.get("code") and item.get("file_path") and item.get("start_line"):
                    item["code"] = get_code_snippet(item["file_path"], item["start_line"], item.get("end_line", 0))
                exact_matches.append(item)
                sources.append(src)

        # 1. First check the Dependency Graph (reusing existing graph resolution)
        try:
            from app.graph.models import NodeType
            active_graph = _resolve_graph(graph, root)
            if active_graph:
                graph_nodes = active_graph.find_nodes_by_name(leaf_name)
                if not graph_nodes and "." in target_name:
                    graph_nodes = active_graph.find_nodes_by_name(target_name)

                for gn in graph_nodes:
                    if gn.node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                        parent_cls = gn.metadata.get("parent_class")
                        if matches_qualifiers(gn.file_path, parent_cls):
                            add_match({
                                "file_path": gn.file_path,
                                "symbol_name": gn.name,
                                "symbol_type": gn.node_type.value.lower(),
                                "parent_symbol": parent_cls,
                                "start_line": gn.start_line or 0,
                                "end_line": gn.end_line or 0,
                                "code": get_code_snippet(gn.file_path, gn.start_line or 0, gn.end_line or 0),
                            }, {
                                "source_type": "graph",
                                "file_path": gn.file_path,
                                "symbol_name": gn.name,
                                "symbol_type": gn.node_type.value.lower(),
                                "parent_symbol": parent_cls,
                                "start_line": gn.start_line or 0,
                                "end_line": gn.end_line or 0,
                            })
        except Exception:
            pass

        # 2. Check AST across project python files (if not found in graph)
        if not exact_matches:
            parser = PythonParser()
            for py_file in root.rglob("*.py"):
                parts_f = [p.lower() for p in py_file.parts]
                if any(p.startswith(".") or p in ("venv", "node_modules", "__pycache__") for p in parts_f):
                    continue
                try:
                    rel_p = py_file.relative_to(root).as_posix()
                    file_info = parser.parse_file(str(py_file))
                    if "error" in file_info:
                        continue

                    # Check classes
                    for cls in file_info.get("classes", []):
                        c_name = cls.get("name", "")
                        c_lower = c_name.lower()
                        if (c_lower == target_name or c_lower == leaf_name) and matches_qualifiers(rel_p, None):
                            add_match({
                                "file_path": rel_p,
                                "symbol_name": c_name,
                                "symbol_type": "class",
                                "parent_symbol": None,
                                "start_line": cls.get("start_line", 0),
                                "end_line": cls.get("end_line", 0),
                                "code": cls.get("code", "") or get_code_snippet(rel_p, cls.get("start_line", 0), cls.get("end_line", 0)),
                            }, {
                                "file_path": rel_p,
                                "symbol_name": c_name,
                                "symbol_type": "class",
                                "parent_symbol": None,
                                "start_line": cls.get("start_line", 0),
                                "end_line": cls.get("end_line", 0),
                            })

                    # Check functions
                    for fn in file_info.get("functions", []):
                        f_name = fn.get("name", "")
                        f_lower = f_name.lower()
                        if (f_lower == target_name or f_lower == leaf_name) and matches_qualifiers(rel_p, None):
                            add_match({
                                "file_path": rel_p,
                                "symbol_name": f_name,
                                "symbol_type": "function",
                                "parent_symbol": None,
                                "start_line": fn.get("start_line", 0),
                                "end_line": fn.get("end_line", 0),
                                "code": fn.get("code", "") or get_code_snippet(rel_p, fn.get("start_line", 0), fn.get("end_line", 0)),
                            }, {
                                "file_path": rel_p,
                                "symbol_name": f_name,
                                "symbol_type": "function",
                                "parent_symbol": None,
                                "start_line": fn.get("start_line", 0),
                                "end_line": fn.get("end_line", 0),
                            })

                    # Check methods
                    for m in file_info.get("methods", []):
                        m_name = m.get("name", "")
                        m_lower = m_name.lower()
                        p_class = m.get("parent_class") or ""
                        p_lower = p_class.lower()
                        full_method = f"{p_lower}.{m_lower}"

                        matched = False
                        if target_name in (m_lower, full_method):
                            matched = True
                        elif leaf_name == m_lower and matches_qualifiers(rel_p, p_class):
                            matched = True

                        if matched:
                            add_match({
                                "file_path": rel_p,
                                "symbol_name": m_name,
                                "symbol_type": "method",
                                "parent_symbol": m.get("parent_class"),
                                "start_line": m.get("start_line", 0),
                                "end_line": m.get("end_line", 0),
                                "code": m.get("code", "") or get_code_snippet(rel_p, m.get("start_line", 0), m.get("end_line", 0)),
                            }, {
                                "file_path": rel_p,
                                "symbol_name": m_name,
                                "symbol_type": "method",
                                "parent_symbol": m.get("parent_class"),
                                "start_line": m.get("start_line", 0),
                                "end_line": m.get("end_line", 0),
                            })
                except Exception:
                    continue

        # 3. Check Qdrant Vector Store payload for exact matches
        if vector_store and vector_store.collection_exists(collection_name):
            try:
                scroll_res = vector_store.client.scroll(
                    collection_name=collection_name,
                    limit=200,
                    with_payload=True,
                    with_vectors=False,
                )
                points = scroll_res[0] if isinstance(scroll_res, tuple) else scroll_res
                for pt in points:
                    payload = pt.payload or {}
                    s_name = payload.get("symbol_name", "")
                    s_lower = s_name.lower()
                    p_symbol = payload.get("parent_symbol", "")
                    p_lower = (p_symbol or "").lower()
                    f_path = payload.get("file_path", "")

                    is_match = False
                    if target_name == s_lower or (p_symbol and target_name == p_lower):
                        is_match = True
                    elif leaf_name == s_lower or (p_symbol and leaf_name == p_lower):
                        if matches_qualifiers(f_path, p_symbol):
                            is_match = True

                    if is_match:
                        add_match({
                            "chunk_id": payload.get("chunk_id", str(pt.id)),
                            "file_path": f_path,
                            "symbol_name": s_name,
                            "symbol_type": payload.get("symbol_type", ""),
                            "parent_symbol": payload.get("parent_symbol"),
                            "start_line": payload.get("start_line", 0),
                            "end_line": payload.get("end_line", 0),
                            "code": payload.get("code", "") or get_code_snippet(f_path, payload.get("start_line", 0), payload.get("end_line", 0)),
                        }, {
                            "chunk_id": payload.get("chunk_id", str(pt.id)),
                            "file_path": f_path,
                            "symbol_name": s_name,
                            "symbol_type": payload.get("symbol_type", ""),
                            "parent_symbol": payload.get("parent_symbol"),
                            "start_line": payload.get("start_line", 0),
                            "end_line": payload.get("end_line", 0),
                        })
            except Exception:
                pass

        if not exact_matches:
            return {
                "data": f"Symbol '{symbol_name}' was not found in the codebase.",
                "sources": [],
            }

        # Sort: source files before test files, exact name match before partial
        exact_matches.sort(key=lambda m: (
            1 if m.get("file_path", "").startswith("tests") or "/tests/" in m.get("file_path", "").replace("\\", "/") else 0,
            0 if m.get("symbol_name", "").lower() == target_name else 1,
        ))

        # Synchronize sources ordering
        sorted_sources = []
        for m in exact_matches:
            for s in sources:
                if s.get("file_path") == m.get("file_path") and s.get("symbol_name") == m.get("symbol_name") and s.get("start_line") == m.get("start_line"):
                    sorted_sources.append(s)
                    break

        return {
            "data": exact_matches,
            "sources": sorted_sources if sorted_sources else sources,
        }

    return {
        "name": "find_symbol",
        "description": "Use this tool to locate a symbol such as a function, class, or method by exact or qualified symbol name.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Exact or qualified name of the function, class, or method to find"},
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


def create_get_file_history_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_file_history tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_file_history_tool(file_path: str, limit: int = 10) -> Dict[str, Any]:
        """Returns recent Git commits that modified a specific file."""
        from app.git.history import get_file_history
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        history = get_file_history(repo=repo, file_path=file_path, limit=limit)
        sources = [
            {
                "source_type": "git",
                "commit_hash": c.commit_hash,
                "short_hash": c.short_hash,
                "author": c.author_name,
                "date": c.date,
                "message": c.message,
                "file_path": history.file_path,
            }
            for c in history.commits
        ]

        return {
            "data": history.to_dict(),
            "sources": sources,
        }

    return {
        "name": "get_file_history",
        "description": "Returns recent Git commits that modified a specific file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the file to inspect Git history for"},
                "limit": {"type": "integer", "minimum": 1, "description": "Maximum number of commits to retrieve (default: 10)"},
            },
            "required": ["file_path"],
        },
        "func": get_file_history_tool,
        "safety_level": "read_only",
    }


def create_get_recent_commits_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_recent_commits tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_recent_commits_tool(limit: int = 10) -> Dict[str, Any]:
        """Returns recent Git commits across the repository."""
        from app.git.history import get_recent_commits
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        commits = get_recent_commits(repo=repo, limit=limit)
        sources = [
            {
                "source_type": "git",
                "commit_hash": c.commit_hash,
                "short_hash": c.short_hash,
                "author": c.author_name,
                "date": c.date,
                "message": c.message,
                "files_changed": c.files_changed,
            }
            for c in commits
        ]

        return {
            "data": [c.to_dict() for c in commits],
            "sources": sources,
        }

    return {
        "name": "get_recent_commits",
        "description": "Returns recent Git commits across the repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "description": "Maximum number of recent commits (default: 10)"},
            },
        },
        "func": get_recent_commits_tool,
        "safety_level": "read_only",
    }


def create_get_last_commit_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_last_commit tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_last_commit_tool(file_path: str) -> Dict[str, Any]:
        """Returns the most recent Git commit that modified a specific file."""
        from app.git.history import get_last_commit_for_file
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        commit = get_last_commit_for_file(repo=repo, file_path=file_path)
        if not commit:
            return {
                "data": f"No commit history found for file: '{file_path}'",
                "sources": [],
            }

        sources = [
            {
                "source_type": "git",
                "commit_hash": commit.commit_hash,
                "short_hash": commit.short_hash,
                "author": commit.author_name,
                "date": commit.date,
                "message": commit.message,
                "file_path": file_path,
            }
        ]

        return {
            "data": commit.to_dict(),
            "sources": sources,
        }

    return {
        "name": "get_last_commit",
        "description": "Returns the most recent Git commit that modified a specific file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the file to inspect"},
            },
            "required": ["file_path"],
        },
        "func": get_last_commit_tool,
        "safety_level": "read_only",
    }


def create_get_commit_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_commit tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_commit_tool(commit_hash: str) -> Dict[str, Any]:
        """Returns metadata and a limited diff for a specific commit."""
        from app.git.history import get_commit_detail
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        detail = get_commit_detail(repo=repo, commit_hash=commit_hash)
        sources = [
            {
                "source_type": "git",
                "commit_hash": detail.commit_hash,
                "short_hash": detail.short_hash,
                "author": detail.author_name,
                "date": detail.date,
                "message": detail.message,
                "files_changed": detail.files_changed,
            }
        ]

        return {
            "data": detail.to_dict(),
            "sources": sources,
        }

    return {
        "name": "get_commit",
        "description": "Returns metadata and a limited diff for a specific commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "commit_hash": {"type": "string", "description": "Full or short SHA hash of the commit"},
            },
            "required": ["commit_hash"],
        },
        "func": get_commit_tool,
        "safety_level": "read_only",
    }


def create_get_file_blame_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_file_blame tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_file_blame_tool(
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Shows which commit and author last modified specific lines."""
        from app.git.history import get_file_blame
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        blame_res = get_file_blame(
            repo=repo,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        )

        seen_commits = set()
        sources = []
        for line in blame_res.lines:
            if line.commit_hash not in seen_commits:
                seen_commits.add(line.commit_hash)
                sources.append({
                    "source_type": "git",
                    "commit_hash": line.commit_hash,
                    "short_hash": line.short_hash,
                    "author": line.author,
                    "date": line.date,
                    "file_path": blame_res.file_path,
                })

        return {
            "data": blame_res.to_dict(),
            "sources": sources,
        }

    return {
        "name": "get_file_blame",
        "description": "Shows which commit and author last modified specific lines in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path of the file to blame"},
                "start_line": {"type": "integer", "minimum": 1, "description": "Optional starting line number (1-indexed)"},
                "end_line": {"type": "integer", "minimum": 1, "description": "Optional ending line number (1-indexed)"},
            },
            "required": ["file_path"],
        },
        "func": get_file_blame_tool,
        "safety_level": "read_only",
    }


def create_git_last_change_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for git_last_change tool."""
    root = (project_root or Path.cwd()).resolve()

    def git_last_change(symbol: str) -> Dict[str, Any]:
        """Returns the most recent Git commit, author, date, and commit message affecting a symbol or file."""
        from app.git.history import get_last_change_for_symbol
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        try:
            active_graph = _resolve_graph(graph, root)
            last_change = get_last_change_for_symbol(repo=repo, symbol=symbol, project_root=root, graph=active_graph)
        except Exception as e:
            return {
                "data": f"Could not retrieve last change for '{symbol}': {str(e)}",
                "sources": [],
            }

        sources = [
            {
                "source_type": "git",
                "symbol_name": symbol,
                "commit_hash": last_change.commit,
                "short_hash": last_change.short_hash,
                "author": last_change.author,
                "date": last_change.date,
                "message": last_change.message,
                "file_path": last_change.file,
                "start_line": last_change.line,
                "end_line": last_change.end_line,
            }
        ]

        return {
            "data": last_change.to_dict(),
            "sources": sources,
        }

    return {
        "name": "git_last_change",
        "description": "Returns the most recent Git commit, author, timestamp, message, and line number affecting a specific symbol or file.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name (e.g. 'GraphBuilder.build') or relative file path (e.g. 'app/graph/builder.py') to inspect last change for"},
            },
            "required": ["symbol"],
        },
        "func": git_last_change,
        "safety_level": "read_only",
    }


def create_git_history_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for git_history tool."""
    root = (project_root or Path.cwd()).resolve()

    def git_history(symbol: str, limit: int = 10) -> Dict[str, Any]:
        """Returns structured commit history affecting a symbol or file."""
        from app.git.history import get_history_for_symbol
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        try:
            active_graph = _resolve_graph(graph, root)
            history_data = get_history_for_symbol(repo=repo, symbol=symbol, limit=limit, project_root=root, graph=active_graph)
        except Exception as e:
            return {
                "data": f"Could not retrieve history for '{symbol}': {str(e)}",
                "sources": [],
            }

        sources = [
            {
                "source_type": "git",
                "symbol_name": symbol,
                "commit_hash": c["commit_hash"],
                "short_hash": c["short_hash"],
                "author": c["author_name"],
                "date": c["date"],
                "message": c["message"],
                "file_path": history_data["file"],
            }
            for c in history_data.get("commits", [])
        ]

        return {
            "data": history_data,
            "sources": sources,
        }

    return {
        "name": "git_history",
        "description": "Returns structured commit history affecting a specific symbol or file.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name (e.g. 'GraphBuilder.build') or relative file path to inspect history for"},
                "limit": {"type": "integer", "minimum": 1, "description": "Maximum number of commits to return (default: 10)"},
            },
            "required": ["symbol"],
        },
        "func": git_history,
        "safety_level": "read_only",
    }


def create_git_blame_symbol_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for git_blame_symbol tool."""
    root = (project_root or Path.cwd()).resolve()

    def git_blame_symbol(
        symbol: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Performs Git blame analysis specifically targeted at a symbol or file."""
        from app.git.history import get_blame_for_symbol
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        try:
            active_graph = _resolve_graph(graph, root)
            blame_data = get_blame_for_symbol(
                repo=repo,
                symbol=symbol,
                start_line=start_line,
                end_line=end_line,
                project_root=root,
                graph=active_graph,
            )
        except Exception as e:
            return {
                "data": f"Could not perform blame for '{symbol}': {str(e)}",
                "sources": [],
            }

        seen_commits = set()
        sources = []
        for line in blame_data.get("lines", []):
            if line["commit_hash"] not in seen_commits:
                seen_commits.add(line["commit_hash"])
                sources.append({
                    "source_type": "git",
                    "symbol_name": symbol,
                    "commit_hash": line["commit_hash"],
                    "short_hash": line["short_hash"],
                    "author": line["author"],
                    "date": line["date"],
                    "file_path": blame_data["file"],
                })

        return {
            "data": blame_data,
            "sources": sources,
        }

    return {
        "name": "git_blame_symbol",
        "description": "Performs Git blame analysis for a specific symbol or file to identify authors, primary contributors, and line-level changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name (e.g. 'GraphBuilder.build') or file path to blame"},
                "start_line": {"type": "integer", "minimum": 1, "description": "Optional starting line number"},
                "end_line": {"type": "integer", "minimum": 1, "description": "Optional ending line number"},
            },
            "required": ["symbol"],
        },
        "func": git_blame_symbol,
        "safety_level": "read_only",
    }


def create_git_show_commit_tool(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for git_show_commit tool."""
    root = (project_root or Path.cwd()).resolve()

    def git_show_commit(commit: str) -> Dict[str, Any]:
        """Returns metadata, diff summary, and statistics for a specific commit hash or revision."""
        from app.git.history import get_commit_detail
        from app.git.repository import NotAGitRepositoryError, get_repository

        try:
            repo = get_repository(root)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }

        try:
            detail = get_commit_detail(repo=repo, commit_hash=commit)
        except Exception as e:
            return {
                "data": f"Could not retrieve commit '{commit}': {str(e)}",
                "sources": [],
            }

        sources = [
            {
                "source_type": "git",
                "commit_hash": detail.commit_hash,
                "short_hash": detail.short_hash,
                "author": detail.author_name,
                "date": detail.date,
                "message": detail.message,
                "files_changed": detail.files_changed,
            }
        ]

        return {
            "data": detail.to_dict(),
            "sources": sources,
        }

    return {
        "name": "git_show_commit",
        "description": "Returns metadata, diff summary, additions, deletions, and changed files for a specific Git commit hash or revision.",
        "parameters": {
            "type": "object",
            "properties": {
                "commit": {"type": "string", "description": "Commit hash or revision (e.g. full SHA, short SHA, or HEAD)"},
            },
            "required": ["commit"],
        },
        "func": git_show_commit,
        "safety_level": "read_only",
    }



_GRAPH_CACHE: Dict[str, Any] = {}


def _resolve_graph(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Any:
    """Helper to obtain or lazily construct a GraphStore."""
    if graph is not None:
        return graph

    from app.graph.builder import GraphBuilder
    from app.graph.store import GraphStore

    root = (project_root or Path.cwd()).resolve()
    root_key = str(root)
    if root_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[root_key]

    default_graph_file = root / "data" / "graph.json"

    if default_graph_file.is_file():
        try:
            g = GraphStore.load(default_graph_file)
            _GRAPH_CACHE[root_key] = g
            return g
        except Exception:
            pass

    g = GraphBuilder().build(root)
    _GRAPH_CACHE[root_key] = g
    return g


def create_get_callers_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_callers tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_callers_tool(symbol: str) -> Dict[str, Any]:
        """Returns functions and methods that directly call the specified symbol."""
        from app.graph.queries import get_callers

        active_graph = _resolve_graph(graph, root)
        callers = get_callers(active_graph, symbol=symbol)

        sources = [
            {
                "source_type": "graph",
                "symbol_name": c["name"],
                "file_path": c["file_path"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "relationship": "CALLER",
            }
            for c in callers
        ]

        if not callers:
            return {
                "data": f"No direct callers found for symbol: '{symbol}'",
                "sources": [],
            }

        return {
            "data": callers,
            "sources": sources,
        }

    return {
        "name": "get_callers",
        "description": "Use this tool when you need to understand which functions or methods call a symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name or ID of the function/method to find callers for"},
            },
            "required": ["symbol"],
        },
        "func": get_callers_tool,
        "safety_level": "read_only",
    }


def create_get_callees_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_callees tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_callees_tool(symbol: str) -> Dict[str, Any]:
        """Returns functions and methods called by the specified symbol."""
        from app.graph.queries import get_callees

        active_graph = _resolve_graph(graph, root)
        callees = get_callees(active_graph, symbol=symbol)

        sources = [
            {
                "source_type": "graph",
                "symbol_name": c["name"],
                "file_path": c["file_path"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "relationship": "CALLEE",
            }
            for c in callees
        ]

        if not callees:
            return {
                "data": f"No outgoing function/method calls found for symbol: '{symbol}'",
                "sources": [],
            }

        return {
            "data": callees,
            "sources": sources,
        }

    return {
        "name": "get_callees",
        "description": "Use this tool when you need to understand which functions, methods, or constructors a symbol calls.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name or ID of the function/method to inspect calls from"},
            },
            "required": ["symbol"],
        },
        "func": get_callees_tool,
        "safety_level": "read_only",
    }


def create_get_dependencies_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_dependencies tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_dependencies_tool(symbol: str, depth: int = 1) -> Dict[str, Any]:
        """Performs multi-step downstream dependency traversal of functions/methods called by the symbol."""
        from app.graph.queries import get_dependencies

        active_graph = _resolve_graph(graph, root)
        dep_result = get_dependencies(active_graph, symbol=symbol, depth=depth)

        sources = [
            {
                "source_type": "graph",
                "symbol_name": d["name"],
                "file_path": d["file_path"],
                "start_line": d["start_line"],
                "end_line": d["end_line"],
                "relationship": f"DEPENDENCY_D{d['depth']}",
            }
            for d in dep_result.get("dependencies", [])
        ]

        return {
            "data": dep_result,
            "sources": sources,
        }

    return {
        "name": "get_dependencies",
        "description": "Use this tool when the user asks what a symbol depends on. Performs multi-step downstream dependency traversal of functions/methods called by a symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name or ID of the root symbol to traverse dependencies for"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum traversal depth (default: 1, max: 10)"},
            },
            "required": ["symbol"],
        },
        "func": get_dependencies_tool,
        "safety_level": "read_only",
    }


def create_get_dependents_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_dependents tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_dependents_tool(symbol: str, depth: int = 1) -> Dict[str, Any]:
        """Performs multi-step upstream reverse dependency traversal (callers) of a symbol."""
        from app.graph.queries import get_dependents

        active_graph = _resolve_graph(graph, root)
        bounded_depth = max(1, min(depth, 10))
        dep_result = get_dependents(active_graph, symbol=symbol, depth=bounded_depth)

        sources = [
            {
                "source_type": "graph",
                "symbol_name": d["name"],
                "file_path": d["file_path"],
                "start_line": d["start_line"],
                "end_line": d["end_line"],
                "relationship": f"DEPENDENT_D{d['depth']}",
            }
            for d in dep_result.get("dependents", [])
        ]

        return {
            "data": dep_result,
            "sources": sources,
        }

    return {
        "name": "get_dependents",
        "description": "Use this tool when the user asks what depends on a symbol. Performs multi-step upstream reverse dependency traversal of functions/methods that call a symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name or ID of the symbol to find reverse dependents for"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum upstream traversal depth (default: 1, max: 10)"},
            },
            "required": ["symbol"],
        },
        "func": get_dependents_tool,
        "safety_level": "read_only",
    }


def create_get_impact_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_impact tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_impact_tool(symbol: str, depth: int = 2) -> Dict[str, Any]:
        """Performs static impact analysis to discover direct and indirect callers affected if a symbol changes."""
        from app.graph.queries import get_impact

        active_graph = _resolve_graph(graph, root)
        bounded_depth = max(1, min(depth, 10))
        impact_result = get_impact(active_graph, symbol=symbol, depth=bounded_depth)

        all_callers = impact_result.get("direct_callers", []) + impact_result.get("indirect_callers", [])
        sources = [
            {
                "source_type": "graph",
                "symbol_name": c["name"],
                "file_path": c["file_path"],
                "start_line": c["start_line"],
                "relationship": f"IMPACT_D{c['depth']}",
            }
            for c in all_callers
        ]

        return {
            "data": impact_result,
            "sources": sources,
        }

    return {
        "name": "get_impact",
        "description": "Use this tool when the user asks what could be affected by changing a symbol. Performs static dependency impact analysis to discover direct and indirect callers affected if a symbol changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Name or ID of the symbol to evaluate impact for"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum upstream traversal depth (default: 2, max: 10)"},
            },
            "required": ["symbol"],
        },
        "func": get_impact_tool,
        "safety_level": "read_only",
    }


def create_get_file_dependencies_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_file_dependencies tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_file_dependencies_tool(file_path: str) -> Dict[str, Any]:
        """Returns imported files, imported modules, and files that import the specified file."""
        from app.graph.queries import get_file_dependencies

        active_graph = _resolve_graph(graph, root)
        file_deps = get_file_dependencies(active_graph, file_path=file_path)

        sources = [
            {
                "source_type": "graph",
                "file_path": f,
                "relationship": "IMPORTED_FILE",
            }
            for f in file_deps.get("imports_files", [])
        ] + [
            {
                "source_type": "graph",
                "file_path": f,
                "relationship": "DEPENDENT_FILE",
            }
            for f in file_deps.get("imported_by", [])
        ]

        return {
            "data": file_deps,
            "sources": sources,
        }

    return {
        "name": "get_file_dependencies",
        "description": "Use this tool when the user asks about dependencies of a file. Returns imported files, imported modules, and dependent files that import the specified file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path of the file to inspect dependency relationships for"},
            },
            "required": ["file_path"],
        },
        "func": get_file_dependencies_tool,
        "safety_level": "read_only",
    }


def create_get_repository_context_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for get_repository_context tool."""
    root = (project_root or Path.cwd()).resolve()

    def get_repository_context_tool(
        question: str,
        symbol: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gathers unified repository intelligence including symbols, source code, graph relations, tests, and Git history."""
        from app.context.engine import ContextEngine

        active_graph = _resolve_graph(graph, root)
        engine = ContextEngine(project_root=root, graph=active_graph)
        context = engine.build_context(
            question=question,
            symbol=symbol,
            file_path=file_path,
        )

        sources: List[Dict[str, Any]] = []

        # Track symbol sources
        for s in context.symbols:
            sources.append({
                "source_type": "symbol",
                "symbol_name": s.name,
                "file_path": s.file_path,
                "start_line": s.start_line,
                "end_line": s.end_line,
            })

        # Track graph callers/callees/deps
        for c in context.callers:
            sources.append({
                "source_type": "graph",
                "symbol_name": c.get("name"),
                "file_path": c.get("file_path"),
                "start_line": c.get("start_line"),
                "relationship": "CALLER",
            })
        for c in context.callees:
            sources.append({
                "source_type": "graph",
                "symbol_name": c.get("name"),
                "file_path": c.get("file_path"),
                "start_line": c.get("start_line"),
                "relationship": "CALLEE",
            })
        for d in context.dependencies:
            sources.append({
                "source_type": "graph",
                "symbol_name": d.get("name"),
                "file_path": d.get("file_path"),
                "start_line": d.get("start_line"),
                "relationship": f"DEPENDENCY_D{d.get('depth', 1)}",
            })

        # Track related tests
        for t in context.related_tests:
            sources.append({
                "source_type": "test",
                "file_path": t.test_file,
                "symbol_name": t.test_function,
                "start_line": t.line_number,
                "relationship": "RELATED_TEST",
            })

        # Track git history
        for g in context.git_history:
            sources.append({
                "source_type": "git",
                "commit_hash": g.commit_hash,
                "short_hash": g.short_hash,
                "author": g.author,
                "date": g.date,
            })

        return {
            "data": context.to_dict(),
            "formatted_text": context.to_formatted_text(),
            "sources": sources,
        }

    return {
        "name": "get_repository_context",
        "description": "Gathers deep repository intelligence combining symbol definitions, source code snippets, dependency graph (callers, callees, dependencies, dependents, impact), related tests, and Git history for a symbol or question.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The user question or topic to gather repository context for"},
                "symbol": {"type": "string", "description": "Optional specific symbol name to focus context gathering on (e.g. 'GraphBuilder.build')"},
                "file_path": {"type": "string", "description": "Optional specific file path to focus context gathering on"},
            },
            "required": ["question"],
        },
        "func": get_repository_context_tool,
        "safety_level": "read_only",
    }


def create_analyze_code_change_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for analyze_code_change tool."""
    root = (project_root or Path.cwd()).resolve()

    def analyze_code_change_tool(commit: str = "HEAD") -> Dict[str, Any]:
        """Analyzes a Git commit for changed symbols, dependency graph impact, and deterministic risk score."""
        from app.changes.analyzer import CodeChangeAnalyzer
        from app.git.repository import NotAGitRepositoryError

        try:
            active_graph = _resolve_graph(graph, root)
            analyzer = CodeChangeAnalyzer(project_root=root)
            analysis = analyzer.analyze_commit(commit_hash=commit or "HEAD", graph=active_graph)
        except NotAGitRepositoryError:
            return {
                "data": "This project is not a Git repository.",
                "sources": [],
            }
        except Exception as e:
            return {
                "data": f"Could not analyze code changes for '{commit}': {str(e)}",
                "sources": [],
            }

        sources = [
            {
                "source_type": "git",
                "commit_hash": analysis.commit,
                "short_hash": analysis.short_hash,
                "author": analysis.author,
                "date": analysis.date,
                "message": analysis.message,
                "files_changed": analysis.changed_files,
            }
        ]

        for sym in analysis.changed_symbols:
            sources.append({
                "source_type": "symbol",
                "symbol_name": sym.name,
                "file_path": sym.file,
                "start_line": sym.line_start,
                "end_line": sym.line_end,
                "relationship": f"CHANGED_{sym.change_type.upper()}",
            })

        return {
            "data": analysis.to_dict(),
            "formatted_text": analysis.to_formatted_text(),
            "sources": sources,
        }

    return {
        "name": "analyze_code_change",
        "description": "Analyzes a Git commit or revision to identify changed symbols, calculate dependency graph impact, and evaluate change risk.",
        "parameters": {
            "type": "object",
            "properties": {
                "commit": {"type": "string", "description": "Git commit hash, short SHA, or revision (e.g. 'HEAD', 'main') to analyze"},
            },
        },
        "func": analyze_code_change_tool,
        "safety_level": "read_only",
    }


def create_semantic_code_search_tool(
    searcher: Optional[SemanticSearcher] = None,
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for semantic_code_search tool (v1.8)."""
    root = (project_root or Path.cwd()).resolve()

    def semantic_code_search_tool(query: str, top_k: int = 5) -> Dict[str, Any]:
        """Performs natural language semantic search for code, functions, classes, and relationships."""
        from app.search.hybrid_search import HybridCodeSearchEngine
        from app.vector_store.qdrant_store import ValidationError

        if not query or not query.strip():
            return {
                "data": "Search query cannot be empty.",
                "sources": [],
            }

        try:
            active_graph = _resolve_graph(graph, root)
            engine = HybridCodeSearchEngine(
                searcher=searcher,
                project_root=root,
                graph=active_graph,
            )
            output = engine.search(query=query, top_k=top_k)
        except ValidationError as e:
            return {
                "data": str(e),
                "sources": [],
            }
        except Exception as e:
            return {
                "data": f"Error performing semantic code search: {str(e)}",
                "sources": [],
            }

        sources = []
        for r in output.results:
            sources.append({
                "source_type": "symbol",
                "symbol_name": r.symbol,
                "file_path": r.file,
                "symbol_type": r.symbol_type,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": round(r.score, 4),
                "related_symbols": r.related_symbols,
            })

        return {
            "data": output.to_dict(),
            "formatted_text": output.to_formatted_text(),
            "sources": sources,
        }

    return {
        "name": "semantic_code_search",
        "description": "Performs semantic / meaning-based code search to find relevant functions, classes, files, and architectural flows for natural language questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query describing what code you are looking for (e.g. 'Where is authentication handled?', 'database connections')"},
                "top_k": {"type": "integer", "minimum": 1, "description": "Max results to return (default: 5)"},
            },
            "required": ["query"],
        },
        "func": semantic_code_search_tool,
        "safety_level": "read_only",
    }


def create_plan_code_change_tool(
    graph: Optional[Any] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Factory for plan_code_change tool (v1.7)."""
    root = (project_root or Path.cwd()).resolve()

    def plan_code_change_tool(change_request: str) -> Dict[str, Any]:
        """Creates a grounded code change implementation plan detailing affected symbols, tests, order, and risk."""
        from app.changes.planner import ChangeImpactPlanner
        from app.vector_store.qdrant_store import ValidationError

        if not change_request or not change_request.strip():
            return {
                "data": "Change request cannot be empty.",
                "sources": [],
            }

        try:
            active_graph = _resolve_graph(graph, root)
            planner = ChangeImpactPlanner(project_root=root)
            plan = planner.plan_change(change_request=change_request, graph=active_graph)
        except ValidationError as e:
            return {
                "data": str(e),
                "sources": [],
            }
        except Exception as e:
            return {
                "data": f"Error planning code change: {str(e)}",
                "sources": [],
            }

        sources = []
        for ev in plan.evidence:
            sources.append({
                "source_type": "graph" if "caller" in ev.relationship.lower() or "test" in ev.relationship.lower() else "code",
                "symbol_name": ev.symbol,
                "file_path": ev.file,
                "lines": ev.lines,
                "relationship": ev.relationship,
            })

        return {
            "data": plan.to_dict(),
            "formatted_text": plan.to_formatted_string(),
            "sources": sources,
        }

    return {
        "name": "plan_code_change",
        "description": "Analyzes a proposed code change or refactoring request and constructs a grounded change plan with affected files, dependent symbols, relevant tests, implementation order, and risk score.",
        "parameters": {
            "type": "object",
            "properties": {
                "change_request": {
                    "type": "string",
                    "description": "Developer change request or refactoring goal (e.g. 'Improve GraphBuilder.build performance', 'Refactor auth.py')",
                },
            },
            "required": ["change_request"],
        },
        "func": plan_code_change_tool,
        "safety_level": "read_only",
    }


def create_review_changes_tool(
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """Factory for the review_changes tool (v1.8)."""

    def review_changes_tool(project_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspects the current Git working tree status, uncommitted diffs, changed symbols,
        dependency impact, risk, and recommended tests.
        """
        from app.changes.reviewer import GitChangeReviewer
        from app.git.repository import NotAGitRepositoryError

        root = (Path(project_dir) if project_dir else (project_root or Path.cwd())).resolve()

        try:
            active_graph = _resolve_graph(graph, root)
            reviewer = GitChangeReviewer(project_root=root)
            review = reviewer.review_working_tree(graph=active_graph)
        except NotAGitRepositoryError as e:
            return {
                "data": str(e),
                "formatted_text": str(e),
                "sources": [],
            }
        except Exception as e:
            return {
                "data": f"Error reviewing code changes: {str(e)}",
                "formatted_text": f"Error reviewing code changes: {str(e)}",
                "sources": [],
            }

        sources = []
        for s in review.changed_symbols:
            sources.append({
                "source_type": "code",
                "symbol_name": s.name,
                "file_path": s.file,
                "lines": f"{s.line_start}-{s.line_end}" if s.line_start else "1",
                "relationship": f"Changed symbol ({s.change_type})",
            })
        for rec in review.test_recommendations:
            sources.append({
                "source_type": "test",
                "symbol_name": rec.symbol_name or rec.test_target,
                "file_path": rec.file_path,
                "lines": "1",
                "relationship": rec.reason,
            })

        return {
            "data": review.to_dict(),
            "formatted_text": review.to_formatted_text(),
            "sources": sources,
        }

    return {
        "name": "review_changes",
        "description": "Performs an intelligent review of current Git working tree changes: inspects git status and diff, extracts modified AST symbols, calculates blast radius impact, evaluates risk (LOW/MEDIUM/HIGH), and recommends test suites.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "func": review_changes_tool,
        "safety_level": "read_only",
    }


def create_autonomous_fix_tool(
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """Factory for the autonomous_fix tool (v1.9)."""

    def autonomous_fix_tool(
        request: str,
        mode: str = "plan",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes the autonomous code fix workflow across PLAN, PATCH, or AUTO modes.
        """
        from app.changes.autonomous_fix import AutonomousFixService
        from app.changes.models import FixMode

        if not request or not request.strip():
            return {
                "data": "Change request cannot be empty.",
                "formatted_text": "Change request cannot be empty.",
                "sources": [],
            }

        root = (project_root or Path.cwd()).resolve()

        try:
            active_graph = _resolve_graph(graph, root)
            service = AutonomousFixService(project_root=root)
            fix_mode = FixMode(mode.upper()) if mode else FixMode.PLAN
            result = service.execute(
                request=request.strip(),
                mode=fix_mode,
                force=force,
                graph=active_graph,
            )
        except Exception as e:
            return {
                "data": f"Error executing autonomous fix: {str(e)}",
                "formatted_text": f"Error executing autonomous fix: {str(e)}",
                "sources": [],
            }

        sources = []
        if result.plan:
            for ev in result.plan.evidence:
                sources.append({
                    "source_type": "graph" if "caller" in ev.relationship.lower() or "test" in ev.relationship.lower() else "code",
                    "symbol_name": ev.symbol,
                    "file_path": ev.file,
                    "lines": ev.lines,
                    "relationship": ev.relationship,
                })
        if result.review:
            for s in result.review.changed_symbols:
                sources.append({
                    "source_type": "code",
                    "symbol_name": s.name,
                    "file_path": s.file,
                    "lines": f"{s.line_start}-{s.line_end}" if s.line_start else "1",
                    "relationship": f"Changed symbol ({s.change_type})",
                })

        return {
            "data": result.to_dict(),
            "formatted_text": result.to_formatted_text(),
            "sources": sources,
        }

    return {
        "name": "autonomous_fix",
        "description": "Coordinates the autonomous code fix loop across PLAN (analyze/plan), PATCH (plan/generate/validate patch), and AUTO (safe apply, test, review, rollback on failure) modes.",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "Natural language fix or refactoring request (e.g. 'Fix the bug in GraphBuilder.build', 'Refactor auth error handling')",
                },
                "mode": {
                    "type": "string",
                    "enum": ["plan", "patch", "auto"],
                    "description": "Fix execution mode: 'plan' (analyze only), 'patch' (plan and generate patch), 'auto' (autonomous apply, test, review, rollback)",
                },
            },
            "required": ["request"],
        },
        "func": autonomous_fix_tool,
        "safety_level": "read_only",
    }




