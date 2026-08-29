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
    resolution_method: Optional[str] = Field(None, description="Target resolution method (exact_qualified, symbol_with_context, exact_unqualified, semantic_search, ambiguous, unresolved)")
    confidence: Optional[float] = Field(None, description="Confidence score of target resolution (0.0 to 1.0)")
    direct_dependencies: List[str] = Field(default_factory=list, description="Direct callees/dependencies")
    affected_files: List[str] = Field(default_factory=list, description="All impacted file paths")
    affected_symbols: List[str] = Field(default_factory=list, description="All impacted symbol names")
    relevant_tests: List[str] = Field(default_factory=list, description="Relevant test suites")
    recommended_order: List[str] = Field(default_factory=list, description="Recommended implementation steps")
    risk: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH)")
    reason: str = Field(..., description="Grounded explanation of change risk")
    evidence: List[ChangePlanEvidenceItem] = Field(default_factory=list, description="Supporting evidence items")
    unverified: List[str] = Field(default_factory=list, description="Unverified claims if any")


class GitStatusSummaryItem(BaseModel):
    branch: str = Field(..., description="Active Git branch")
    base_branch: Optional[str] = Field(None, description="Tracking/base branch")
    is_clean: bool = Field(..., description="True if working tree is clean")
    modified_files: List[str] = Field(default_factory=list)
    added_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    renamed_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    staged_files: List[str] = Field(default_factory=list)
    unstaged_files: List[str] = Field(default_factory=list)
    ahead_commits: int = Field(default=0)
    behind_commits: int = Field(default=0)


class TestRecommendationItem(BaseModel):
    test_target: str = Field(..., description="Test target identifier or file path")
    file_path: str = Field(..., description="Test file path")
    reason: str = Field(..., description="Rationale for recommending this test")
    symbol_name: Optional[str] = Field(None, description="Associated symbol name")


class ReviewChangeRequest(BaseModel):
    project_dir: str = Field(default=".", description="Target project directory")


class ReviewChangeResponse(BaseModel):
    branch: str = Field(..., description="Active Git branch")
    base_branch: Optional[str] = Field(None, description="Tracking/base branch")
    is_clean: bool = Field(..., description="True if working tree is clean")
    status: GitStatusSummaryItem = Field(..., description="Working tree status summary")
    changed_files: List[str] = Field(default_factory=list, description="Changed file paths")
    changed_symbols: List[ChangedSymbolItem] = Field(default_factory=list, description="Changed AST symbols")
    impact: ChangeImpactItem = Field(..., description="Calculated dependency impact")
    risk: ChangeRiskItem = Field(..., description="Evaluated change risk")
    recommended_tests: List[str] = Field(default_factory=list, description="List of recommended test targets")
    test_recommendations: List[TestRecommendationItem] = Field(default_factory=list, description="Detailed test recommendations")
    diff_stats: dict = Field(default_factory=dict, description="Diff line additions and deletions")
    review_notes: List[str] = Field(default_factory=list, description="Specific review findings/warnings")
    summary: str = Field(..., description="Narrative review summary")


class AutonomousFixRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Developer fix or refactoring request")
    mode: str = Field(default="plan", description="Fix execution mode: 'plan', 'patch', or 'auto'")
    force: bool = Field(default=False, description="Force execution even if working tree is dirty")
    project_dir: str = Field(default=".", description="Target project directory")


class AutonomousFixResponse(BaseModel):
    mode: str = Field(..., description="Fix mode (PLAN, PATCH, AUTO)")
    status: str = Field(..., description="Execution status (success, plan_only, patch_only, failed, refused_dirty_tree, rolled_back)")
    request: str = Field(..., description="Original user fix request")
    phase: str = Field(..., description="Last executed phase")
    applied: bool = Field(default=False, description="Whether the patch was applied")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings encountered")
    message: str = Field(default="", description="Summary message")
    data: Optional[dict] = Field(default=None, description="Raw fix execution payload")

