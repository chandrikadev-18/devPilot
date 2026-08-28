"""
DevPilot Git Intelligence API Schemas.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GitCommitInfoSchema(BaseModel):
    commit_hash: str = Field(..., description="Full SHA hash")
    short_hash: str = Field(..., description="Short 7-char SHA hash")
    author_name: str = Field(..., description="Author name")
    author_email: Optional[str] = Field(None, description="Author email")
    date: str = Field(..., description="Commit date timestamp")
    message: str = Field(..., description="Commit message")
    files_changed: List[str] = Field(default_factory=list, description="List of files modified")


class GitLastChangeResponse(BaseModel):
    symbol: str = Field(..., description="Target symbol or file path")
    commit: str = Field(..., description="Full commit SHA")
    short_hash: str = Field(..., description="Short 7-char commit SHA")
    author: str = Field(..., description="Author of the last change")
    date: str = Field(..., description="Commit timestamp")
    message: str = Field(..., description="Commit message")
    file: str = Field(..., description="Relative file path")
    line: Optional[int] = Field(None, description="Starting line number")
    end_line: Optional[int] = Field(None, description="Ending line number")


class GitHistoryResponse(BaseModel):
    symbol: str = Field(..., description="Target symbol or file path")
    file: str = Field(..., description="Resolved file path")
    line: Optional[int] = Field(None, description="Symbol start line if applicable")
    total_commits: int = Field(..., description="Total number of commits found")
    commits: List[GitCommitInfoSchema] = Field(default_factory=list, description="Chronological list of commits")


class GitBlameLineSchema(BaseModel):
    line_number: int = Field(..., description="Line number (1-indexed)")
    commit_hash: str = Field(..., description="Commit SHA")
    short_hash: str = Field(..., description="Short commit SHA")
    author: str = Field(..., description="Line author")
    date: str = Field(..., description="Commit timestamp")
    content: str = Field(..., description="Line source code content")


class GitBlameResponse(BaseModel):
    symbol: str = Field(..., description="Target symbol or file path")
    file: str = Field(..., description="Resolved file path")
    start_line: Optional[int] = Field(None, description="Start line number")
    end_line: Optional[int] = Field(None, description="End line number")
    total_lines: int = Field(..., description="Total blamed lines")
    primary_contributor: str = Field(..., description="Top contributor for this symbol/file")
    contributors: List[str] = Field(default_factory=list, description="List of distinct contributors")
    lines: List[GitBlameLineSchema] = Field(default_factory=list, description="Line-by-line blame records")


class GitCommitDetailResponse(BaseModel):
    commit_hash: str = Field(..., description="Full commit SHA")
    short_hash: str = Field(..., description="Short 7-char SHA")
    author_name: str = Field(..., description="Author name")
    author_email: Optional[str] = Field(None, description="Author email")
    date: str = Field(..., description="Commit timestamp")
    message: str = Field(..., description="Commit message")
    files_changed: List[str] = Field(default_factory=list, description="List of modified files")
    additions: int = Field(default=0, description="Number of lines added")
    deletions: int = Field(default=0, description="Number of lines deleted")
    diff_summary: str = Field(default="", description="Patch/diff summary")
    truncated: bool = Field(default=False, description="Whether diff was truncated due to size limit")
