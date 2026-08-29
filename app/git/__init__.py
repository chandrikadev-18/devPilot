"""
DevPilot Git Intelligence Module.

Provides read-only access to Git repository history, commit metadata,
file change tracking, blame inspection, and working tree change detection.
"""

from app.git.change_detector import GitChangeDetector
from app.git.history import (
    MAX_DIFF_CHARACTERS,
    get_blame_for_symbol,
    get_commit_detail,
    get_file_blame,
    get_file_history,
    get_history_for_symbol,
    get_last_change_for_symbol,
    get_last_commit_for_file,
    get_recent_commits,
    resolve_symbol_location,
)
from app.git.models import (
    BlameLine,
    BlameResult,
    ChangeSummary,
    ChangeType,
    CommitDetail,
    CommitInfo,
    FileHistoryResult,
    GitChange,
    SymbolLastChangeResult,
)
from app.git.repository import (
    GitBlameError,
    GitCommitNotFoundError,
    GitError,
    GitFileNotFoundError,
    GitRepository,
    GitSecurityError,
    NotAGitRepositoryError,
    get_repository,
    is_git_repository,
)

__all__ = [
    "MAX_DIFF_CHARACTERS",
    "GitError",
    "NotAGitRepositoryError",
    "GitSecurityError",
    "GitCommitNotFoundError",
    "GitFileNotFoundError",
    "GitBlameError",
    "GitRepository",
    "is_git_repository",
    "get_repository",
    "CommitInfo",
    "FileHistoryResult",
    "BlameLine",
    "BlameResult",
    "CommitDetail",
    "SymbolLastChangeResult",
    "ChangeType",
    "GitChange",
    "ChangeSummary",
    "GitChangeDetector",
    "get_recent_commits",
    "get_file_history",
    "get_last_commit_for_file",
    "get_commit_detail",
    "get_file_blame",
    "resolve_symbol_location",
    "get_last_change_for_symbol",
    "get_history_for_symbol",
    "get_blame_for_symbol",
]
