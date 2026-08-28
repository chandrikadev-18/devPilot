"""
DevPilot Git History Operations.

Implements read-only Git history querying, blame inspection,
commit detail retrieval, and diff formatting with bounded limits.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import git

from app.git.models import (
    BlameLine,
    BlameResult,
    CommitDetail,
    CommitInfo,
    FileHistoryResult,
    SymbolLastChangeResult,
)
from app.git.repository import (
    GitBlameError,
    GitCommitNotFoundError,
    GitError,
    GitFileNotFoundError,
    GitRepository,
)

MAX_DIFF_CHARACTERS = 12000


def _format_commit_date(epoch_seconds: int) -> str:
    """Formats epoch seconds into standard ISO-8601 UTC timestamp."""
    dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _commit_to_commit_info(commit: git.Commit) -> CommitInfo:
    """Extracts structured CommitInfo from a GitPython Commit object."""
    files_changed: List[str] = []
    try:
        if commit.parents:
            # Files changed relative to primary parent
            diffs = commit.parents[0].diff(commit)
            files_changed = [d.b_path or d.a_path for d in diffs if d.b_path or d.a_path]
        else:
            # Initial commit - all files in stats
            files_changed = list(commit.stats.files.keys())
    except Exception:
        # Fallback to stats if diff fails
        try:
            files_changed = list(commit.stats.files.keys())
        except Exception:
            files_changed = []

    author_name = commit.author.name if commit.author else "Unknown"
    author_email = commit.author.email if commit.author else ""
    date_str = _format_commit_date(commit.committed_date)

    return CommitInfo(
        commit_hash=commit.hexsha,
        short_hash=commit.hexsha[:7],
        author_name=author_name,
        author_email=author_email,
        date=date_str,
        message=commit.message.strip() if commit.message else "",
        files_changed=files_changed,
    )


def get_recent_commits(
    repo: GitRepository,
    limit: int = 10,
) -> List[CommitInfo]:
    """
    Retrieves the most recent commits in repository history.
    """
    max_count = max(1, limit)
    results: List[CommitInfo] = []

    try:
        for commit in repo.raw_repo.iter_commits(max_count=max_count):
            results.append(_commit_to_commit_info(commit))
    except git.GitCommandError as e:
        # e.g., empty repository with no commits yet
        if "does not have any commits" in str(e) or "bad revision 'HEAD'" in str(e):
            return []
        raise GitError(f"Failed to retrieve commits: {e}") from e
    except Exception as e:
        raise GitError(f"Error querying commit history: {e}") from e

    return results


def get_file_history(
    repo: GitRepository,
    file_path: str,
    limit: int = 10,
) -> FileHistoryResult:
    """
    Retrieves the commit history affecting a specific file.
    """
    rel_path = repo.resolve_safe_relpath(file_path)
    full_path = repo.root / rel_path

    # Check if file exists in working tree or historical commits
    max_count = max(1, limit)
    commits: List[CommitInfo] = []

    try:
        for commit in repo.raw_repo.iter_commits(paths=rel_path, max_count=max_count):
            commits.append(_commit_to_commit_info(commit))
    except git.GitCommandError as e:
        if "does not have any commits" in str(e) or "bad revision 'HEAD'" in str(e):
            return FileHistoryResult(file_path=rel_path, commits=[], total_commits=0)
        raise GitError(f"Failed to retrieve file history for '{rel_path}': {e}") from e
    except Exception as e:
        raise GitError(f"Error querying history for '{rel_path}': {e}") from e

    if not commits and not full_path.exists():
        raise GitFileNotFoundError(f"File not found in repository or history: '{file_path}'")

    return FileHistoryResult(
        file_path=rel_path,
        commits=commits,
        total_commits=len(commits),
    )


def get_last_commit_for_file(
    repo: GitRepository,
    file_path: str,
) -> Optional[CommitInfo]:
    """
    Retrieves the most recent commit that modified a specific file.
    """
    history = get_file_history(repo=repo, file_path=file_path, limit=1)
    if history.commits:
        return history.commits[0]
    return None


def get_commit_detail(
    repo: GitRepository,
    commit_hash: str,
    max_diff_chars: int = MAX_DIFF_CHARACTERS,
) -> CommitDetail:
    """
    Retrieves detailed metadata, statistics, and diff summary for a specific commit.
    Safely truncates diffs exceeding max_diff_chars.
    """
    if not commit_hash or not commit_hash.strip():
        raise GitCommitNotFoundError("Commit hash cannot be empty.")

    target_hash = commit_hash.strip()

    try:
        commit = repo.raw_repo.commit(target_hash)
        # Force evaluation of lazy GitPython commit object
        _ = commit.committed_date
    except (git.BadName, git.BadObject, ValueError, KeyError, IndexError) as e:
        raise GitCommitNotFoundError(f"Commit not found: '{commit_hash}'") from e
    except git.GitCommandError as e:
        if "bad revision" in str(e).lower() or "unknown revision" in str(e).lower() or "bad object" in str(e).lower() or "not found" in str(e).lower():
            raise GitCommitNotFoundError(f"Commit not found: '{commit_hash}'") from e
        raise GitError(f"Error accessing commit '{commit_hash}': {e}") from e
    except Exception as e:
        raise GitCommitNotFoundError(f"Commit not found: '{commit_hash}'") from e

    # Extract stats
    additions = 0
    deletions = 0
    files_changed: List[str] = []

    try:
        stats = commit.stats
        additions = stats.total.get("insertions", 0)
        deletions = stats.total.get("deletions", 0)
        files_changed = list(stats.files.keys())
    except Exception:
        pass

    # Extract diff
    diff_text_chunks: List[str] = []
    try:
        if commit.parents:
            parent = commit.parents[0]
            diff_index = parent.diff(commit, create_patch=True)
            for diff_item in diff_index:
                header = f"--- {diff_item.a_path or 'dev/null'}\n+++ {diff_item.b_path or 'dev/null'}\n"
                patch = diff_item.diff.decode("utf-8", errors="replace") if isinstance(diff_item.diff, bytes) else str(diff_item.diff or "")
                diff_text_chunks.append(header + patch)
        else:
            # Initial root commit
            diff_index = commit.diff(git.NULL_TREE, create_patch=True, reverse=True)
            for diff_item in diff_index:
                header = f"--- /dev/null\n+++ {diff_item.b_path or diff_item.a_path}\n"
                patch = diff_item.diff.decode("utf-8", errors="replace") if isinstance(diff_item.diff, bytes) else str(diff_item.diff or "")
                diff_text_chunks.append(header + patch)
    except Exception as e:
        diff_text_chunks.append(f"[Diff could not be rendered: {e}]")

    raw_diff = "\n".join(diff_text_chunks).strip()

    truncated = False
    if len(raw_diff) > max_diff_chars:
        raw_diff = raw_diff[:max_diff_chars].rstrip() + "\n\n[diff truncated]"
        truncated = True

    author_name = commit.author.name if commit.author else "Unknown"
    author_email = commit.author.email if commit.author else ""
    date_str = _format_commit_date(commit.committed_date)

    return CommitDetail(
        commit_hash=commit.hexsha,
        short_hash=commit.hexsha[:7],
        author_name=author_name,
        author_email=author_email,
        date=date_str,
        message=commit.message.strip() if commit.message else "",
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
        diff_summary=raw_diff,
        truncated=truncated,
    )


def get_file_blame(
    repo: GitRepository,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> BlameResult:
    """
    Performs line-level Git blame analysis on a file, with optional line range bounds.
    """
    rel_path = repo.resolve_safe_relpath(file_path)
    full_path = repo.root / rel_path

    if not full_path.exists():
        raise GitFileNotFoundError(f"File not found: '{file_path}'")

    if full_path.is_dir():
        raise GitError(f"Path is a directory, not a file: '{file_path}'")

    # Validate line numbers if provided
    if start_line is not None and start_line < 1:
        raise GitBlameError(f"start_line must be >= 1, got {start_line}")
    if start_line is not None and end_line is not None and end_line < start_line:
        raise GitBlameError(f"end_line ({end_line}) cannot be less than start_line ({start_line})")

    try:
        # Execute blame over HEAD
        blame_entries = repo.raw_repo.blame("HEAD", rel_path)
    except git.GitCommandError as e:
        if "no such path" in str(e).lower() or "not found" in str(e).lower():
            raise GitFileNotFoundError(f"File '{rel_path}' is not tracked in Git history.") from e
        raise GitBlameError(f"Git blame failed for '{rel_path}': {e}") from e
    except Exception as e:
        raise GitBlameError(f"Error blaming '{rel_path}': {e}") from e

    all_lines: List[BlameLine] = []
    current_line_num = 1

    for commit, lines in blame_entries:
        c_hash = commit.hexsha
        s_hash = commit.hexsha[:7]
        author = commit.author.name if commit.author else "Unknown"
        date_str = _format_commit_date(commit.committed_date)

        for line in lines:
            line_str = line if isinstance(line, str) else str(line)
            all_lines.append(
                BlameLine(
                    line_number=current_line_num,
                    commit_hash=c_hash,
                    short_hash=s_hash,
                    author=author,
                    date=date_str,
                    content=line_str,
                )
            )
            current_line_num += 1

    total_lines = len(all_lines)

    if start_line is not None and start_line > total_lines and total_lines > 0:
        raise GitBlameError(f"start_line ({start_line}) exceeds file line count ({total_lines})")

    # Filter lines according to bounds
    filtered_lines = all_lines
    if start_line is not None:
        filtered_lines = [l for l in filtered_lines if l.line_number >= start_line]
    if end_line is not None:
        filtered_lines = [l for l in filtered_lines if l.line_number <= end_line]

    return BlameResult(
        file_path=rel_path,
        lines=filtered_lines,
        start_line=start_line,
        end_line=end_line,
    )


def resolve_symbol_location(
    symbol: str,
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> Optional[Tuple[str, int, int]]:
    """
    Resolves a symbol name or file path to its relative file path, start line, and end line.
    Returns (file_path, start_line, end_line) or None if unresolvable.
    """
    if not symbol or not symbol.strip():
        return None

    root = (project_root or Path.cwd()).resolve()
    cleaned = symbol.strip().replace("\\", "/")

    # 1. Direct file path check
    direct_path = (root / cleaned).resolve()
    if direct_path.is_file():
        try:
            rel = direct_path.relative_to(root).as_posix()
            lines = direct_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return (rel, 1, max(1, len(lines)))
        except Exception:
            pass

    # 2. Check Dependency Graph
    try:
        from app.graph.models import NodeType
        active_graph = graph
        if active_graph is None:
            from app.agent.tools import _resolve_graph
            active_graph = _resolve_graph(None, root)

        if active_graph:
            leaf = cleaned.split(".")[-1].lower()
            nodes = active_graph.find_nodes_by_name(leaf)
            if not nodes and "." in cleaned:
                nodes = active_graph.find_nodes_by_name(cleaned.lower())

            for n in nodes:
                if n.node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                    s_line = n.start_line or 1
                    e_line = n.end_line or (s_line + 30)
                    return (n.file_path, s_line, e_line)
    except Exception:
        pass

    # 3. Search AST across Python files in project_root
    try:
        from app.parser.python_parser import PythonParser
        parser = PythonParser()
        leaf = cleaned.split(".")[-1].lower()
        for pf in root.rglob("*.py"):
            rel_p = pf.relative_to(root).as_posix()
            if rel_p.startswith((".venv", "venv", ".git", "build", "dist")):
                continue
            parsed = parser.parse_file(str(pf))
            # Classes
            for cls in parsed.get("classes", []):
                if cls["name"].lower() == leaf or (cleaned.lower() in cls["name"].lower()):
                    s_line = cls.get("line_number", 1)
                    return (rel_p, s_line, s_line + 30)
            # Functions / Methods
            for fn in parsed.get("functions", []) + parsed.get("methods", []):
                if fn["name"].lower() == leaf:
                    s_line = fn.get("line_number", 1)
                    return (rel_p, s_line, s_line + 30)
    except Exception:
        pass

    return None


def get_last_change_for_symbol(
    repo: GitRepository,
    symbol: str,
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> SymbolLastChangeResult:
    """
    Finds the most recent Git commit, author, date, and commit message affecting a symbol or file.
    """
    if not symbol or not symbol.strip():
        raise GitError("Symbol or file path cannot be empty.")

    root = project_root or repo.root
    location = resolve_symbol_location(symbol, project_root=root, graph=graph)

    if location is None:
        rel_path = repo.resolve_safe_relpath(symbol)
        full_path = repo.root / rel_path
        if not full_path.exists():
            raise GitFileNotFoundError(f"Symbol or file not found in codebase: '{symbol}'")
        location = (rel_path, 1, 1)

    file_path, start_line, end_line = location

    # Try Git blame on the exact definition line
    try:
        blame_res = get_file_blame(repo, file_path=file_path, start_line=start_line, end_line=start_line)
        if blame_res.lines:
            target_line = blame_res.lines[0]
            commit_hash = target_line.commit_hash
            short_hash = target_line.short_hash
            author = target_line.author
            date = target_line.date
            message = ""
            try:
                c_obj = repo.raw_repo.commit(commit_hash)
                message = c_obj.message.strip() if c_obj.message else ""
            except Exception:
                pass

            return SymbolLastChangeResult(
                symbol=symbol,
                commit=commit_hash,
                short_hash=short_hash,
                author=author,
                date=date,
                message=message,
                file=file_path,
                line=start_line,
                end_line=end_line,
            )
    except Exception:
        pass

    # Fallback to last commit for file
    last_commit = get_last_commit_for_file(repo, file_path=file_path)
    if last_commit:
        return SymbolLastChangeResult(
            symbol=symbol,
            commit=last_commit.commit_hash,
            short_hash=last_commit.short_hash,
            author=last_commit.author_name,
            date=last_commit.date,
            message=last_commit.message,
            file=file_path,
            line=start_line,
            end_line=end_line,
        )

    raise GitError(f"No Git history found for '{symbol}' in '{file_path}'.")


def get_history_for_symbol(
    repo: GitRepository,
    symbol: str,
    limit: int = 10,
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Retrieves commit history for a symbol or file.
    """
    root = project_root or repo.root
    location = resolve_symbol_location(symbol, project_root=root, graph=graph)
    if location is None:
        rel_path = repo.resolve_safe_relpath(symbol)
        full_path = repo.root / rel_path
        if not full_path.exists():
            raise GitFileNotFoundError(f"Symbol or file not found in codebase: '{symbol}'")
        location = (rel_path, 1, 1)

    file_path, start_line, end_line = location
    history_res = get_file_history(repo, file_path=file_path, limit=limit)
    return {
        "symbol": symbol,
        "file": file_path,
        "line": start_line,
        "total_commits": history_res.total_commits,
        "commits": [c.to_dict() for c in history_res.commits],
    }


def get_blame_for_symbol(
    repo: GitRepository,
    symbol: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    project_root: Optional[Path] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Performs Git blame analysis specifically targeted at a symbol or file.
    """
    root = project_root or repo.root
    location = resolve_symbol_location(symbol, project_root=root, graph=graph)
    if location is None:
        rel_path = repo.resolve_safe_relpath(symbol)
        full_path = repo.root / rel_path
        if not full_path.exists():
            raise GitFileNotFoundError(f"Symbol or file not found in codebase: '{symbol}'")
        location = (rel_path, start_line or 1, end_line or 1)

    file_path, sym_start, sym_end = location
    s_line = start_line if start_line is not None else sym_start
    e_line = end_line if end_line is not None else sym_end

    blame_res = get_file_blame(repo, file_path=file_path, start_line=s_line, end_line=e_line)

    author_counts: Dict[str, int] = {}
    for line in blame_res.lines:
        author_counts[line.author] = author_counts.get(line.author, 0) + 1

    top_author = max(author_counts.items(), key=lambda item: item[1])[0] if author_counts else "Unknown"

    return {
        "symbol": symbol,
        "file": file_path,
        "start_line": s_line,
        "end_line": e_line,
        "total_lines": blame_res.to_dict()["total_lines"],
        "primary_contributor": top_author,
        "contributors": list(author_counts.keys()),
        "lines": blame_res.to_dict()["lines"],
    }

