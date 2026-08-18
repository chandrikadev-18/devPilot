"""
DevPilot Git Data Models.

Provides structured, JSON-serializable dataclasses for Git commits,
file histories, blame analyses, and diff summaries.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CommitInfo:
    """
    Structured metadata for a single Git commit.
    """
    commit_hash: str
    short_hash: str
    author_name: str
    author_email: str
    date: str
    message: str
    files_changed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts CommitInfo to a clean serializable dictionary."""
        return {
            "commit_hash": self.commit_hash,
            "short_hash": self.short_hash,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "date": self.date,
            "message": self.message,
            "files_changed": self.files_changed,
        }


@dataclass
class FileHistoryResult:
    """
    Structured result representing the commit history of a specific file.
    """
    file_path: str
    commits: List[CommitInfo] = field(default_factory=list)
    total_commits: int = 0

    def __post_init__(self):
        if not self.total_commits and self.commits:
            self.total_commits = len(self.commits)

    def to_dict(self) -> Dict[str, Any]:
        """Converts FileHistoryResult to a clean serializable dictionary."""
        return {
            "file_path": self.file_path,
            "total_commits": self.total_commits,
            "commits": [c.to_dict() for c in self.commits],
        }


@dataclass
class BlameLine:
    """
    Line-level Git blame information.
    """
    line_number: int
    commit_hash: str
    short_hash: str
    author: str
    date: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts BlameLine to a clean serializable dictionary."""
        return {
            "line_number": self.line_number,
            "commit_hash": self.commit_hash,
            "short_hash": self.short_hash,
            "author": self.author,
            "date": self.date,
            "content": self.content,
        }


@dataclass
class BlameResult:
    """
    Structured result of a Git blame inspection over a file or line range.
    """
    file_path: str
    lines: List[BlameLine] = field(default_factory=list)
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts BlameResult to a clean serializable dictionary."""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "total_lines": len(self.lines),
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass
class CommitDetail:
    """
    Detailed inspection of a commit including metadata, statistics, and diff.
    """
    commit_hash: str
    short_hash: str
    author_name: str
    author_email: str
    date: str
    message: str
    files_changed: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    diff_summary: str = ""
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Converts CommitDetail to a clean serializable dictionary."""
        return {
            "commit_hash": self.commit_hash,
            "short_hash": self.short_hash,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "date": self.date,
            "message": self.message,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff_summary": self.diff_summary,
            "truncated": self.truncated,
        }
