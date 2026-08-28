"""
DevPilot Symbol-Level Change Detector.

Inspects Git commits and diffs using AST parsing to identify added, modified,
deleted, and renamed symbols.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import git

from app.changes.models import ChangedSymbol, SymbolChangeType
from app.git.repository import GitCommitNotFoundError, GitError, GitRepository
from app.parser.python_parser import PythonParser


def _extract_symbols_map(ast_data: dict, rel_path: str) -> Dict[str, dict]:
    """
    Transforms AST parse dictionary into a map of canonical symbol names to symbol descriptors.
    """
    symbols: Dict[str, dict] = {}

    for cls in ast_data.get("classes", []):
        name = cls["name"]
        symbols[name] = {
            "name": name,
            "file": rel_path,
            "type": "class",
            "start_line": cls.get("start_line", 1),
            "end_line": cls.get("end_line", 1),
            "source": cls.get("source", "").strip(),
        }

    for fn in ast_data.get("functions", []):
        name = fn["name"]
        symbols[name] = {
            "name": name,
            "file": rel_path,
            "type": "function",
            "start_line": fn.get("start_line", 1),
            "end_line": fn.get("end_line", 1),
            "source": fn.get("source", "").strip(),
        }

    for m in ast_data.get("methods", []):
        parent = m.get("parent_class", "")
        name = m["name"]
        full_name = f"{parent}.{name}" if parent else name
        symbols[full_name] = {
            "name": full_name,
            "file": rel_path,
            "type": "method",
            "start_line": m.get("start_line", 1),
            "end_line": m.get("end_line", 1),
            "source": m.get("source", "").strip(),
        }

    return symbols


def detect_changed_symbols(
    repo: GitRepository,
    commit_hash: str = "HEAD",
) -> Tuple[List[str], List[ChangedSymbol]]:
    """
    Analyzes a Git commit and detects all changed files and AST symbols.
    Returns (changed_files, changed_symbols).
    """
    if not commit_hash or not commit_hash.strip():
        raise GitCommitNotFoundError("Commit hash cannot be empty.")

    target_hash = commit_hash.strip()
    try:
        commit = repo.raw_repo.commit(target_hash)
        _ = commit.committed_date
    except Exception as e:
        raise GitCommitNotFoundError(f"Commit not found: '{commit_hash}'") from e

    parser = PythonParser()
    changed_files: List[str] = []
    changed_symbols: List[ChangedSymbol] = []
    seen_symbol_keys: Set[str] = set()

    try:
        if commit.parents:
            parent = commit.parents[0]
            diff_index = parent.diff(commit)
        else:
            diff_index = commit.diff(git.NULL_TREE, reverse=True)
    except Exception as e:
        raise GitError(f"Error computing diff for commit '{commit_hash}': {e}") from e

    for diff_item in diff_index:
        file_a = (diff_item.a_path or "").replace("\\", "/")
        file_b = (diff_item.b_path or "").replace("\\", "/")
        primary_file = file_b or file_a

        if not primary_file:
            continue

        changed_files.append(primary_file)

        # Only parse Python files for symbol changes
        if not primary_file.endswith(".py"):
            continue

        # Check if file was deleted
        if diff_item.deleted_file:
            try:
                a_data = diff_item.a_blob.data_stream.read() if diff_item.a_blob else b""
                parsed_a = parser.parse_code(a_data, file_a)
                symbols_a = _extract_symbols_map(parsed_a, file_a)
                for sym_name, sym_info in symbols_a.items():
                    k = f"{sym_info['file']}:{sym_name}"
                    if k not in seen_symbol_keys:
                        seen_symbol_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=sym_info["file"],
                                change_type=SymbolChangeType.DELETED.value,
                                symbol_type=sym_info["type"],
                                line_start=sym_info["start_line"],
                                line_end=sym_info["end_line"],
                            )
                        )
            except Exception:
                pass
            continue

        # Check if file was added
        if diff_item.new_file:
            try:
                b_data = diff_item.b_blob.data_stream.read() if diff_item.b_blob else b""
                parsed_b = parser.parse_code(b_data, file_b)
                symbols_b = _extract_symbols_map(parsed_b, file_b)
                for sym_name, sym_info in symbols_b.items():
                    k = f"{sym_info['file']}:{sym_name}"
                    if k not in seen_symbol_keys:
                        seen_symbol_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=sym_info["file"],
                                change_type=SymbolChangeType.ADDED.value,
                                symbol_type=sym_info["type"],
                                line_start=sym_info["start_line"],
                                line_end=sym_info["end_line"],
                            )
                        )
            except Exception:
                pass
            continue

        # File was modified or renamed
        try:
            a_data = diff_item.a_blob.data_stream.read() if diff_item.a_blob else b""
            b_data = diff_item.b_blob.data_stream.read() if diff_item.b_blob else b""
            parsed_a = parser.parse_code(a_data, file_a)
            parsed_b = parser.parse_code(b_data, file_b)
            symbols_a = _extract_symbols_map(parsed_a, file_a)
            symbols_b = _extract_symbols_map(parsed_b, file_b)

            is_renamed_file = getattr(diff_item, "renamed_file", False) or file_a != file_b

            # Check for added symbols in modified file
            for sym_name, sym_b in symbols_b.items():
                if sym_name not in symbols_a:
                    k = f"{sym_b['file']}:{sym_name}"
                    if k not in seen_symbol_keys:
                        seen_symbol_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=sym_b["file"],
                                change_type=SymbolChangeType.ADDED.value,
                                symbol_type=sym_b["type"],
                                line_start=sym_b["start_line"],
                                line_end=sym_b["end_line"],
                            )
                        )
                else:
                    # In both: check if source changed
                    sym_a = symbols_a[sym_name]
                    if sym_a["source"] != sym_b["source"] or sym_a["start_line"] != sym_b["start_line"]:
                        k = f"{sym_b['file']}:{sym_name}"
                        if k not in seen_symbol_keys:
                            seen_symbol_keys.add(k)
                            c_type = SymbolChangeType.RENAMED.value if is_renamed_file else SymbolChangeType.MODIFIED.value
                            changed_symbols.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=sym_b["file"],
                                    change_type=c_type,
                                    symbol_type=sym_b["type"],
                                    line_start=sym_b["start_line"],
                                    line_end=sym_b["end_line"],
                                )
                            )

            # Check for deleted symbols in modified file
            for sym_name, sym_a in symbols_a.items():
                if sym_name not in symbols_b:
                    k = f"{file_a}:{sym_name}"
                    if k not in seen_symbol_keys:
                        seen_symbol_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=file_a,
                                change_type=SymbolChangeType.DELETED.value,
                                symbol_type=sym_a["type"],
                                line_start=sym_a["start_line"],
                                line_end=sym_a["end_line"],
                            )
                        )
        except Exception:
            pass

    return changed_files, changed_symbols
