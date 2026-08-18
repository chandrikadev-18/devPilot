"""
DevPilot Git Intelligence Module.

Provides read-only access to Git repository history, commit metadata,
file change tracking, and blame inspection.
"""

from app.git.history import (
    MAX_DIFF_CHARACTERS,
    get_commit_detail,
    get_file_blame,
    get_file_history,
    get_last_commit_for_file,
    get_recent_commits,
)
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
    "get_recent_commits",
    "get_file_history",
    "get_last_commit_for_file",
    "get_commit_detail",
    "get_file_blame",
]
