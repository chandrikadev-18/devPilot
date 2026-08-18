"""
DevPilot Git History Operations.

Implements read-only Git history querying, blame inspection,
commit detail retrieval, and diff formatting with bounded limits.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import git

from app.git.models import (
    BlameLine,
    BlameResult,
    CommitDetail,
    CommitInfo,
    FileHistoryResult,
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
    except (git.BadName, ValueError) as e:
        raise GitCommitNotFoundError(f"Commit not found: '{commit_hash}'") from e
    except Exception as e:
        raise GitError(f"Error accessing commit '{commit_hash}': {e}") from e

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
