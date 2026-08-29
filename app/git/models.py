"""
DevPilot Git Data Models.

Provides structured, JSON-serializable dataclasses for Git commits,
file histories, blame analyses, working tree changes, and change summaries.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChangeType(str, Enum):
    """Supported Git working tree file change types."""
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


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


@dataclass
class SymbolLastChangeResult:
    """
    Structured result of the last Git change affecting a specific symbol or file.
    """
    symbol: str
    commit: str
    short_hash: str
    author: str
    date: str
    message: str
    file: str
    line: Optional[int] = None
    end_line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts SymbolLastChangeResult to a clean serializable dictionary."""
        return {
            "symbol": self.symbol,
            "commit": self.commit,
            "short_hash": self.short_hash,
            "author": self.author,
            "date": self.date,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass
class GitChange:
    """
    Represents a single changed file in the Git working tree.
    """
    file_path: str
    change_type: str = "MODIFIED"  # ADDED, MODIFIED, DELETED, RENAMED
    staged: bool = False
    unstaged: bool = True
    additions: int = 0
    deletions: int = 0
    diff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts GitChange to a clean serializable dictionary."""
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "staged": self.staged,
            "unstaged": self.unstaged,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff": self.diff,
        }


@dataclass
class ChangeSummary:
    """
    Structured summary of Git working tree changes, changed symbols,
    dependency blast radius impact, test intelligence, and risk.
    """
    branch: str = "main"
    current_branch: Optional[str] = None
    changed_files: List[GitChange] = field(default_factory=list)
    changed_symbols: List[str] = field(default_factory=list)
    impacted_symbols: List[str] = field(default_factory=list)
    impacted_files: List[str] = field(default_factory=list)
    relevant_tests: List[str] = field(default_factory=list)
    risk: str = "LOW"  # LOW, MEDIUM, HIGH
    risk_reason: str = ""
    warnings: List[str] = field(default_factory=list)
    recommendation: str = ""
    direct_impact_count: int = 0
    indirect_impact_count: int = 0
    impacted_files_count: int = 0

    def __post_init__(self):
        if not self.current_branch:
            self.current_branch = self.branch
        if not self.direct_impact_count and self.impacted_symbols:
            self.direct_impact_count = len(self.impacted_symbols)
        if not self.impacted_files_count and self.impacted_files:
            self.impacted_files_count = len(self.impacted_files)

    def to_dict(self) -> Dict[str, Any]:
        """Converts ChangeSummary to stable machine-readable JSON dictionary."""
        return {
            "branch": self.branch,
            "changed_files": [f.to_dict() if isinstance(f, GitChange) else f for f in self.changed_files],
            "changed_symbols": self.changed_symbols,
            "impacted_symbols": self.impacted_symbols,
            "impacted_files": self.impacted_files,
            "relevant_tests": self.relevant_tests,
            "risk": self.risk,
            "risk_reason": self.risk_reason,
            "warnings": self.warnings,
        }

    def to_formatted_text(self) -> str:
        """Renders the DevPilot v2.0 human-readable CLI output."""
        if not self.changed_files and not self.changed_symbols:
            return "No uncommitted changes detected."

        lines = [
            "DevPilot v2.0 — Git Change Intelligence",
            "────────────────────────────────────────",
            "",
            "Branch:",
            self.branch or "HEAD",
            "",
            f"Changed Files: {len(self.changed_files)}",
            "",
        ]

        for cf in self.changed_files:
            ctype = cf.change_type if isinstance(cf, GitChange) else cf.get("change_type", "MODIFIED")
            fpath = cf.file_path if isinstance(cf, GitChange) else cf.get("file_path", "")
            lines.append(f"{ctype:<9} {fpath}")

        lines.extend(["", "Changed Symbols:"])
        if not self.changed_symbols:
            lines.append("  (None detected)")
        else:
            for s in self.changed_symbols:
                lines.append(f"  {s}")

        lines.extend([
            "",
            "Impact:",
            f"  Direct: {self.direct_impact_count}",
            f"  Indirect: {self.indirect_impact_count}",
            f"  Files: {self.impacted_files_count}",
        ])

        lines.extend(["", "Relevant Tests:"])
        if not self.relevant_tests:
            lines.append("  (None detected)")
        else:
            for t in self.relevant_tests:
                lines.append(f"  {t}")

        lines.extend([
            "",
            "Risk:",
            f"  {self.risk}",
        ])

        if self.risk_reason:
            lines.extend([
                "",
                "Reasons:",
            ])
            for r in self.risk_reason.split("\n"):
                if r.strip():
                    lines.append(f"  - {r.strip().lstrip('- ')}")

        rec = self.recommendation or "Run the affected test suites before committing."
        lines.extend([
            "",
            "Recommendation:",
            f"  {rec}",
        ])

        if self.warnings:
            lines.extend(["", "Warnings:"])
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")

        return "\n".join(lines)
