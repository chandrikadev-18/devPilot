"""
DevPilot Code Change Intelligence API Schemas.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyzeChangeRequest(BaseModel):
    commit: str = Field(default="HEAD", description="Git commit hash, short SHA, or revision to analyze")
    project_dir: str = Field(default=".", description="Target project directory")


class ChangedSymbolItem(BaseModel):
    name: str = Field(..., description="Canonical symbol name (e.g. 'GraphBuilder.build')")
    file: str = Field(..., description="File path relative to repository root")
    change_type: str = Field(..., description="Change type (added, modified, deleted, renamed)")
    symbol_type: str = Field(..., description="Symbol type (function, method, class)")
    line_start: Optional[int] = Field(None, description="Starting line number")
    line_end: Optional[int] = Field(None, description="Ending line number")


class ChangeImpactItem(BaseModel):
    direct: List[str] = Field(default_factory=list, description="Direct callers / dependents")
    indirect: List[str] = Field(default_factory=list, description="Indirect callers / dependents")
    files: List[str] = Field(default_factory=list, description="Impacted file paths")
    total_affected_symbols: int = Field(default=0, description="Total unique affected symbols")


class ChangeRiskItem(BaseModel):
    score: int = Field(..., ge=0, le=100, description="Deterministic risk score (0-100)")
    level: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH, CRITICAL)")
    reasons: List[str] = Field(default_factory=list, description="Reasons contributing to risk score")


class AnalyzeChangeResponse(BaseModel):
    commit: str = Field(..., description="Full commit SHA")
    short_hash: str = Field(..., description="Short 7-char commit SHA")
    author: str = Field(..., description="Commit author")
    date: str = Field(..., description="Commit timestamp")
    message: str = Field(..., description="Commit message")
    changed_files: List[str] = Field(default_factory=list, description="List of modified files")
    changed_symbols: List[ChangedSymbolItem] = Field(default_factory=list, description="List of changed AST symbols")
    impact: ChangeImpactItem = Field(..., description="Static dependency impact analysis")
    risk: ChangeRiskItem = Field(..., description="Calculated change risk evaluation")


class PlanChangeRequest(BaseModel):
    change_request: str = Field(..., min_length=1, description="Developer change request or refactoring goal")
    project_dir: str = Field(default=".", description="Target project directory")


class ChangePlanEvidenceItem(BaseModel):
    file: str = Field(..., description="File path")
    symbol: str = Field(..., description="Symbol name")
    lines: str = Field(..., description="Line span")
    relationship: str = Field(..., description="Relationship description")


class PlanChangeResponse(BaseModel):
    change_request: str = Field(..., description="Original change request")
    target: str = Field(..., description="Resolved target symbol or file")
    target_symbol: Optional[str] = Field(None, description="Resolved target symbol name")
    target_file: Optional[str] = Field(None, description="Resolved target file path")
    target_lines: Optional[str] = Field(None, description="Target line span")
    affected_files: List[str] = Field(default_factory=list, description="All impacted file paths")
    affected_symbols: List[str] = Field(default_factory=list, description="All impacted symbol names")
    relevant_tests: List[str] = Field(default_factory=list, description="Relevant test suites")
    recommended_order: List[str] = Field(default_factory=list, description="Recommended implementation steps")
    risk: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH)")
    reason: str = Field(..., description="Grounded explanation of change risk")
    evidence: List[ChangePlanEvidenceItem] = Field(default_factory=list, description="Supporting evidence items")
    unverified: List[str] = Field(default_factory=list, description="Unverified claims if any")

