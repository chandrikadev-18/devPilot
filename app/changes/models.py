"""
DevPilot Code Change Intelligence Models.

Data models for symbol-level change detection, static dependency impact,
and deterministic risk evaluation.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional


class SymbolChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ChangedSymbol:
    """
    Represents a specific syntactic symbol (function, method, class) altered in a commit.
    """
    name: str
    file: str
    change_type: str = "modified"
    symbol_type: str = "function"
    line_start: Optional[int] = None
    line_end: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "change_type": self.change_type,
            "symbol_type": self.symbol_type,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }


@dataclass
class ChangeImpact:
    """
    Represents the calculated dependency graph impact of the changed symbols.
    """
    direct_dependents: List[str] = field(default_factory=list)
    indirect_dependents: List[str] = field(default_factory=list)
    impacted_files: List[str] = field(default_factory=list)
    total_affected_symbols: int = 0

    def __post_init__(self):
        if not self.total_affected_symbols:
            all_syms = set(self.direct_dependents) | set(self.indirect_dependents)
            self.total_affected_symbols = len(all_syms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direct": self.direct_dependents,
            "indirect": self.indirect_dependents,
            "files": self.impacted_files,
            "total_affected_symbols": self.total_affected_symbols,
        }


@dataclass
class ChangeRisk:
    """
    Deterministic risk score and categorization for a commit.
    """
    score: int = 0
    level: str = "LOW"
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "reasons": self.reasons,
        }


@dataclass
class CodeChangeAnalysis:
    """
    Comprehensive change intelligence report combining Git commit metadata,
    changed symbols, graph impact, and deterministic risk score.
    """
    commit: str
    short_hash: str
    author: str
    date: str
    message: str
    changed_files: List[str] = field(default_factory=list)
    changed_symbols: List[ChangedSymbol] = field(default_factory=list)
    impact: ChangeImpact = field(default_factory=ChangeImpact)
    risk: ChangeRisk = field(default_factory=ChangeRisk)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit": self.commit,
            "short_hash": self.short_hash,
            "author": self.author,
            "date": self.date,
            "message": self.message,
            "changed_files": self.changed_files,
            "changed_symbols": [s.to_dict() for s in self.changed_symbols],
            "impact": self.impact.to_dict(),
            "risk": self.risk.to_dict(),
        }

    def to_formatted_text(self) -> str:
        """Renders a clean human-readable summary for CLI and LLM prompts."""
        lines = [
            f"Commit:  {self.short_hash} ({self.commit})",
            f"Author:  {self.author}",
            f"Date:    {self.date}",
            f"Message: {self.message}",
            "",
            f"Changed Files ({len(self.changed_files)}):",
        ]
        for f in self.changed_files:
            lines.append(f"  • {f}")

        lines.append(f"\nChanged Symbols ({len(self.changed_symbols)}):")
        if not self.changed_symbols:
            lines.append("  • (No Python symbol definitions changed)")
        else:
            for s in self.changed_symbols:
                loc = f" ({s.file}:{s.line_start})" if s.line_start else f" ({s.file})"
                lines.append(f"  • [{s.change_type.upper()}] {s.name}{loc}")

        lines.extend([
            "",
            "Impact Analysis:",
            f"  Direct Dependents:   {len(self.impact.direct_dependents)}",
            f"  Indirect Dependents: {len(self.impact.indirect_dependents)}",
            f"  Impacted Files:      {len(self.impact.impacted_files)}",
        ])

        if self.impact.direct_dependents:
            lines.append("  Key Direct Callers:")
            for d in self.impact.direct_dependents[:8]:
                lines.append(f"    - {d}")
            if len(self.impact.direct_dependents) > 8:
                lines.append(f"    ... and {len(self.impact.direct_dependents) - 8} more")

        lines.extend([
            "",
            f"Risk Level: {self.risk.level} ({self.risk.score}/100)",
            "Risk Reasons:",
        ])
        for r in self.risk.reasons:
            lines.append(f"  • {r}")

        return "\n".join(lines)


@dataclass
class ChangePlanEvidence:
    """
    Verified code/graph evidence supporting a code change plan.
    """
    file: str
    symbol: str
    lines: str
    relationship: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "symbol": self.symbol,
            "lines": self.lines,
            "relationship": self.relationship,
        }


@dataclass
class CodeChangePlan:
    """
    Grounded code change plan detailing affected symbols, impacted files,
    relevant tests, recommended implementation order, and risk level.
    """
    change_request: str
    target_symbol: str = ""
    target_file: str = ""
    target_lines: Optional[str] = None
    resolution_method: Optional[str] = None
    confidence: Optional[float] = None
    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    relevant_tests: List[str] = field(default_factory=list)
    recommended_order: List[str] = field(default_factory=list)
    direct_dependencies: List[str] = field(default_factory=list)
    risk: str = "LOW"
    reason: str = ""
    evidence: List[ChangePlanEvidence] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)

    @property
    def target(self) -> str:
        return self.target_symbol or self.target_file or "Unknown"

    def to_formatted_string(self) -> str:
        """Renders the required DevPilot v1.7/v1.8 change plan output format."""
        sections = [
            f"Change Request:\n{self.change_request}",
            f"Target:\n{self.target_symbol or self.target_file or 'Unknown'}",
        ]

        if self.affected_files:
            af_lines = ["Affected Files:"] + [f"- {f}" for f in self.affected_files]
            sections.append("\n".join(af_lines))
        else:
            sections.append("Affected Files:\n- None")

        if self.affected_symbols:
            as_lines = ["Affected Symbols:"] + [f"- {s}" for s in self.affected_symbols]
            sections.append("\n".join(as_lines))
        else:
            sections.append("Affected Symbols:\n- None")

        if self.relevant_tests:
            rt_lines = ["Relevant Tests:"] + [f"- {t}" for t in self.relevant_tests]
            sections.append("\n".join(rt_lines))
        else:
            sections.append("Relevant Tests:\n- None identified")

        if self.recommended_order:
            ro_lines = ["Recommended Change Order:"] + [f"{i}. {step}" for i, step in enumerate(self.recommended_order, 1)]
            sections.append("\n".join(ro_lines))

        sections.append(f"Risk:\n{self.risk}")
        sections.append(f"Reason:\n{self.reason}")

        if self.evidence:
            ev_lines = ["Evidence:"]
            for ev in self.evidence:
                ev_lines.append(
                    f"- File: {ev.file}\n"
                    f"  Symbol: {ev.symbol}\n"
                    f"  Lines: {ev.lines}\n"
                    f"  Relationship: {ev.relationship}"
                )
            sections.append("\n".join(ev_lines))

        if self.unverified:
            unv_lines = ["Unverified:"] + [f"- {u}" for u in self.unverified]
            sections.append("\n".join(unv_lines))

        return "\n\n".join(sections)

    def to_markdown_plan(self) -> str:
        """Renders change plan in structured Markdown format."""
        loc = f"{self.target_file}:{self.target_lines}" if (self.target_file and self.target_lines) else (self.target_file or "Unknown")
        target_name = self.target_symbol or self.target_file or "Unknown"

        lines = [
            "## Change Plan",
            "",
            "### Target",
            f"`{target_name}`",
            "",
            "### Current Location",
            f"`{loc}`",
            "",
            "### Direct Dependencies",
        ]
        if self.direct_dependencies:
            for dep in self.direct_dependencies:
                lines.append(f"- `{dep}`")
        else:
            lines.append("- (None identified)")

        lines.extend(["", "### Direct Dependents"])
        if self.affected_symbols:
            for dep in self.affected_symbols[:8]:
                lines.append(f"- `{dep}`")
            if len(self.affected_symbols) > 8:
                lines.append(f"- ... and {len(self.affected_symbols) - 8} more")
        else:
            lines.append("- (None identified)")

        lines.extend(["", "### Indirect Impact"])
        if self.affected_files:
            for f in self.affected_files:
                lines.append(f"- `{f}`")
        else:
            lines.append("- (Isolated to target component)")

        lines.extend(["", "### Relevant Tests"])
        if self.relevant_tests:
            for t in self.relevant_tests:
                lines.append(f"- `{t}`")
        else:
            lines.append("- (None identified)")

        lines.extend([
            "",
            "### Risk",
            f"**{self.risk}**",
            "",
            "### Recommended Change Sequence",
        ])
        if self.recommended_order:
            for i, step in enumerate(self.recommended_order, 1):
                lines.append(f"{i}. {step}")
        else:
            lines.extend([
                f"1. Implement core logic changes in `{target_name}` ({loc})",
                "2. Verify and update direct dependencies",
                "3. Update and verify direct dependents",
                "4. Run relevant tests",
                "5. Review diff and validate repository health",
            ])

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_request": self.change_request,
            "target": self.target_symbol or self.target_file or "Unknown",
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "target_lines": self.target_lines,
            "resolution_method": self.resolution_method,
            "confidence": self.confidence,
            "direct_dependencies": self.direct_dependencies,
            "affected_files": self.affected_files,
            "affected_symbols": self.affected_symbols,
            "relevant_tests": self.relevant_tests,
            "recommended_order": self.recommended_order,
            "risk": self.risk,
            "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence],
            "unverified": self.unverified,
        }


@dataclass
class FileChangeItem:
    """
    Describes a single file-level proposed change.
    """
    file: str
    description: str
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "description": self.description,
            "explanation": self.explanation,
        }


@dataclass
class CodeChangeProposal:
    """
    Reviewable code change proposal and unified diff patch.
    """
    change_request: str
    target: str
    risk: str
    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    changes: List[FileChangeItem] = field(default_factory=list)
    patch: str = ""
    tests_to_run: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""

    @property
    def patch_diff(self) -> str:
        return self.patch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_request": self.change_request,
            "target": self.target,
            "risk": self.risk,
            "affected_files": self.affected_files,
            "affected_symbols": self.affected_symbols,
            "changes": [c.to_dict() for c in self.changes],
            "patch": self.patch,
            "tests_to_run": self.tests_to_run,
            "warnings": self.warnings,
        }

    def to_formatted_text(self) -> str:
        """Renders human-readable change proposal with reviewable patch summary."""
        sections = [
            f"Change Request:\n{self.change_request}",
            f"Target:\n{self.target}",
            f"Risk:\n{self.risk}",
        ]

        if self.affected_files:
            af_lines = ["Affected Files:"] + [f"- {f}" for f in self.affected_files]
            sections.append("\n".join(af_lines))
        else:
            sections.append("Affected Files:\n- None")

        if self.affected_symbols:
            as_lines = ["Affected Symbols:"] + [f"- {s}" for s in self.affected_symbols]
            sections.append("\n".join(as_lines))
        else:
            sections.append("Affected Symbols:\n- None")

        if self.changes:
            ch_lines = ["Proposed Modifications:"]
            for ch in self.changes:
                ch_lines.append(f"- File: {ch.file}\n  What: {ch.description}")
                if ch.explanation:
                    ch_lines.append(f"  Why:  {ch.explanation}")
            sections.append("\n".join(ch_lines))

        if self.patch:
            sections.append(f"Proposed Patch (Unified Diff):\n```diff\n{self.patch.strip()}\n```")
        elif not self.warnings:
            sections.append("Proposed Patch:\n(No code modifications required)")

        if self.tests_to_run:
            t_lines = ["Tests to Run:"] + [f"- {t}" for t in self.tests_to_run]
            sections.append("\n".join(t_lines))

        if self.warnings:
            w_lines = ["Warnings:"] + [f"- {w}" for w in self.warnings]
            sections.append("\n".join(w_lines))

        return "\n\n".join(sections)


class ProposalStatus(str, Enum):
    PROPOSAL_ONLY = "PROPOSAL_ONLY"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ChangeProposal:
    """
    Structured, reviewable code change proposal generated from a natural language request (v2.1 & v2.2).
    """
    request: str
    proposal_id: Optional[str] = None
    target_symbol: Optional[str] = None
    target_file: Optional[str] = None
    target_lines: Optional[str] = None
    change_summary: str = ""
    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    proposed_changes: List[str] = field(default_factory=list)
    patch: str = ""
    tests_to_update: List[str] = field(default_factory=list)
    tests_to_add: List[str] = field(default_factory=list)
    risk: str = "LOW"
    reasoning: str = ""
    confidence: Optional[float] = 1.0
    warnings: List[str] = field(default_factory=list)
    unverified_assumptions: List[str] = field(default_factory=list)
    status: str = "PENDING_APPROVAL"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    applied_at: Optional[str] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    target_content_hash: Optional[str] = None

    @property
    def target(self) -> str:
        if self.target_symbol and self.target_file:
            loc = f":{self.target_lines}" if self.target_lines else ""
            return f"{self.target_symbol} ({self.target_file}{loc})"
        return self.target_symbol or self.target_file or "Unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Converts ChangeProposal to a clean, stable JSON serializable dictionary."""
        d = {
            "proposal_id": self.proposal_id,
            "request": self.request,
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "target_lines": self.target_lines,
            "change_summary": self.change_summary,
            "affected_files": self.affected_files,
            "affected_symbols": self.affected_symbols,
            "proposed_changes": self.proposed_changes,
            "patch": self.patch,
            "tests_to_update": self.tests_to_update,
            "tests_to_add": self.tests_to_add,
            "risk": self.risk,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "warnings": self.warnings,
            "unverified_assumptions": self.unverified_assumptions,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "applied_at": self.applied_at,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "target_content_hash": self.target_content_hash,
        }
        return d

    def to_formatted_text(self) -> str:
        """Renders DevPilot Change Proposal formatted text."""
        lines = [
            "DevPilot v2.1 — Change Proposal",
            "────────────────────────────────",
            "",
        ]

        if self.proposal_id:
            lines.extend([
                f"Proposal ID:\n{self.proposal_id}",
                "",
            ])

        lines.extend([
            "Request:",
            self.request,
            "",
            "Target:",
        ])

        if self.target_symbol and self.target_file:
            loc = f":{self.target_lines}" if self.target_lines else ""
            lines.append(self.target_symbol)
            lines.append(f"{self.target_file}{loc}")
        elif self.target_file:
            loc = f":{self.target_lines}" if self.target_lines else ""
            lines.append(f"{self.target_file}{loc}")
        else:
            lines.append(self.target_symbol or "Unknown")

        lines.extend([
            "",
            "Risk:",
            self.risk,
            "",
            "Proposed Changes:",
        ])

        if self.proposed_changes:
            for idx, ch in enumerate(self.proposed_changes, start=1):
                # Clean if already prefixed with a number
                ch_text = re.sub(r"^\d+\.\s*", "", ch)
                lines.append(f"{idx}. {ch_text}")
        else:
            lines.append("1. (No specific modifications proposed)")

        lines.extend(["", "Files:"])
        if self.affected_files:
            for f in self.affected_files:
                lines.append(f"- {f}")
        elif self.target_file:
            lines.append(f"- {self.target_file}")
        else:
            lines.append("- (None)")

        lines.extend(["", "Tests:"])
        all_tests = list(self.tests_to_update) + list(self.tests_to_add)
        if all_tests:
            for t in all_tests:
                lines.append(f"- {t}")
        else:
            lines.append("- (None identified)")

        lines.extend(["", "Patch:"])
        if self.patch and self.patch.strip():
            lines.append(self.patch.strip())
        else:
            lines.append("(No patch generated)")

        lines.extend([
            "",
            "Status:",
            self.status,
        ])

        if self.decision_reason:
            lines.extend([
                "",
                f"Decision Note:\n{self.decision_reason}",
            ])

        if self.warnings:
            lines.extend(["", "Warnings:"])
            for w in self.warnings:
                lines.append(f"⚠ {w}")

        return "\n".join(lines)


@dataclass
class PatchValidationResult:
    """
    Result of pre-application validation checks on a unified diff patch.
    """
    is_valid: bool = True
    status: str = "SAFE TO APPLY"  # SAFE TO APPLY / VALIDATION FAILED / STALE
    files_affected: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)

    @property
    def affected_files(self) -> List[str]:
        return self.files_affected

    @property
    def lines_added(self) -> int:
        return self.additions

    @property
    def lines_deleted(self) -> int:
        return self.deletions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status": self.status,
            "files_affected": self.files_affected,
            "additions": self.additions,
            "deletions": self.deletions,
            "warnings": self.warnings,
            "errors": self.errors,
            "conflicts": self.conflicts,
        }

    def to_formatted_text(self) -> str:
        lines = [
            "DevPilot v1.7",
            "────────────────────────────────",
            "",
            "Patch Validation",
            "",
            "Files affected:",
        ]
        if self.files_affected:
            for f in self.files_affected:
                lines.append(f"  {f}")
        else:
            lines.append("  (None)")

        lines.extend([
            "",
            "Changes:",
            f"  + {self.additions} lines",
            f"  - {self.deletions} lines",
            "",
            "Status:",
            f"  {self.status}",
        ])

        if self.conflicts:
            lines.extend(["", "Conflicts:"])
            for c in self.conflicts:
                lines.append(f"  ⚠ {c}")

        if self.warnings:
            lines.extend(["", "Warnings:"])
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")

        if self.errors:
            lines.extend(["", "Errors:"])
            for e in self.errors:
                lines.append(f"  ✗ {e}")

        lines.extend(["", "Dry run:", "  No files were modified."])
        return "\n".join(lines)


@dataclass
class TestValidationResult:
    """
    Structured outcome of post-application test suite execution.
    """
    __test__ = False
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    execution_time: float = 0.0
    exit_code: int = 0
    is_success: bool = True
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "execution_time": self.execution_time,
            "exit_code": self.exit_code,
            "is_success": self.is_success,
        }


@dataclass
class PatchApplicationResult:
    """
    Comprehensive record of patch application, post-apply test validation, and rollback status.
    """
    status: str = "success"  # success, cancelled, validation_failed, tests_failed, rolled_back
    applied: bool = False
    files_changed: List[str] = field(default_factory=list)
    tests: Optional[Dict[str, Any]] = None
    rollback_available: bool = False
    checkpoint_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "status": self.status,
            "applied": self.applied,
            "files_changed": self.files_changed,
        }
        if self.tests is not None:
            d["tests"] = self.tests
        if self.rollback_available is not None:
            d["rollback_available"] = self.rollback_available
        if self.errors:
            d["errors"] = self.errors
        if self.warnings:
            d["warnings"] = self.warnings
        return d


@dataclass
class RollbackResult:
    """
    Outcome of reverting a DevPilot-applied patch from a backup checkpoint.
    """
    status: str = "success"  # success, no_checkpoint, failed
    reverted_files: List[str] = field(default_factory=list)
    checkpoint_id: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reverted_files": self.reverted_files,
            "checkpoint_id": self.checkpoint_id,
            "message": self.message,
        }


@dataclass
class GitStatusSummary:
    """
    Summarizes Git working tree file statuses.
    """
    branch: str = "main"
    base_branch: Optional[str] = None
    is_clean: bool = True
    modified_files: List[str] = field(default_factory=list)
    added_files: List[str] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    renamed_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    staged_files: List[str] = field(default_factory=list)
    unstaged_files: List[str] = field(default_factory=list)
    ahead_commits: int = 0
    behind_commits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch": self.branch,
            "base_branch": self.base_branch,
            "is_clean": self.is_clean,
            "modified_files": self.modified_files,
            "added_files": self.added_files,
            "deleted_files": self.deleted_files,
            "renamed_files": self.renamed_files,
            "untracked_files": self.untracked_files,
            "staged_files": self.staged_files,
            "unstaged_files": self.unstaged_files,
            "ahead_commits": self.ahead_commits,
            "behind_commits": self.behind_commits,
        }


@dataclass
class TestRecommendation:
    """
    Recommended test suite or function based on repository relationships.
    """
    __test__ = False
    test_target: str
    file_path: str
    reason: str
    symbol_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_target": self.test_target,
            "file_path": self.file_path,
            "reason": self.reason,
            "symbol_name": self.symbol_name,
        }


@dataclass
class GitChangeReview:
    """
    Comprehensive intelligent review of current Git working tree changes.
    """
    branch: str
    base_branch: Optional[str] = None
    is_clean: bool = True
    status: GitStatusSummary = field(default_factory=GitStatusSummary)
    changed_files: List[str] = field(default_factory=list)
    changed_symbols: List[ChangedSymbol] = field(default_factory=list)
    impact: ChangeImpact = field(default_factory=ChangeImpact)
    risk: ChangeRisk = field(default_factory=ChangeRisk)
    recommended_tests: List[str] = field(default_factory=list)
    test_recommendations: List[TestRecommendation] = field(default_factory=list)
    diff_stats: Dict[str, int] = field(default_factory=lambda: {"additions": 0, "deletions": 0})
    diff_summary: str = ""
    review_notes: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch": self.branch,
            "base_branch": self.base_branch,
            "is_clean": self.is_clean,
            "status": self.status.to_dict(),
            "changed_files": self.changed_files,
            "changed_symbols": [s.to_dict() for s in self.changed_symbols],
            "impact": self.impact.to_dict(),
            "risk": self.risk.to_dict(),
            "recommended_tests": self.recommended_tests,
            "test_recommendations": [t.to_dict() for t in self.test_recommendations],
            "diff_stats": self.diff_stats,
            "diff_summary": self.diff_summary,
            "review_notes": self.review_notes,
            "summary": self.summary,
        }

    def to_formatted_text(self) -> str:
        lines = [
            "DevPilot v1.8 — Git Change Review",
            "───────────────────────────────────",
            f"Branch: {self.branch}" + (f" (Tracking: {self.base_branch})" if self.base_branch else ""),
        ]

        if self.is_clean:
            lines.extend([
                "Working Tree: Clean (No uncommitted changes)",
                "",
                "Status:",
                "  • Staged changes: 0",
                "  • Unstaged changes: 0",
                "  • Untracked files: 0",
                "",
                f"Risk: {self.risk.level} ({self.risk.score}/100)",
                f"Reason: {self.risk.reasons[0] if self.risk.reasons else 'Clean repository: No uncommitted changes.'}",
            ])
            return "\n".join(lines)

        lines.extend([
            f"Working Tree: {len(self.changed_files)} changed file(s)",
            "",
            "Summary of Changes:",
        ])
        if self.status.modified_files:
            lines.append(f"  Modified:  {', '.join(self.status.modified_files)}")
        if self.status.added_files:
            lines.append(f"  Added:     {', '.join(self.status.added_files)}")
        if self.status.deleted_files:
            lines.append(f"  Deleted:   {', '.join(self.status.deleted_files)}")
        if self.status.renamed_files:
            lines.append(f"  Renamed:   {', '.join(self.status.renamed_files)}")
        if self.status.untracked_files:
            lines.append(f"  Untracked: {', '.join(self.status.untracked_files)}")
        if self.status.staged_files:
            lines.append(f"  Staged:    {', '.join(self.status.staged_files)}")
        if self.status.unstaged_files:
            lines.append(f"  Unstaged:  {', '.join(self.status.unstaged_files)}")

        lines.append(f"  Diff:      +{self.diff_stats.get('additions', 0)} lines, -{self.diff_stats.get('deletions', 0)} lines")

        lines.append(f"\nChanged Symbols ({len(self.changed_symbols)}):")
        if not self.changed_symbols:
            lines.append("  • (No Python symbol definitions altered)")
        else:
            for s in self.changed_symbols:
                loc = f" ({s.file}:{s.line_start})" if s.line_start else f" ({s.file})"
                lines.append(f"  • [{s.change_type.upper()}] {s.name}{loc}")

        lines.extend([
            "",
            "Dependency & Blast Radius Impact:",
            f"  Direct Dependents:   {len(self.impact.direct_dependents)}",
            f"  Indirect Dependents: {len(self.impact.indirect_dependents)}",
            f"  Impacted Files:      {len(self.impact.impacted_files)}",
        ])

        if self.impact.direct_dependents:
            lines.append("  Key Direct Callers:")
            for d in self.impact.direct_dependents[:8]:
                lines.append(f"    - {d}")
            if len(self.impact.direct_dependents) > 8:
                lines.append(f"    ... and {len(self.impact.direct_dependents) - 8} more")

        lines.extend([
            "",
            f"Risk Level: {self.risk.level} ({self.risk.score}/100)",
            "Risk Reasons:",
        ])
        for r in self.risk.reasons:
            lines.append(f"  • {r}")

        lines.extend([
            "",
            f"Recommended Tests ({len(self.recommended_tests)}):",
        ])
        if not self.recommended_tests:
            lines.append("  • (No specific automated tests identified)")
        else:
            for t in self.recommended_tests:
                lines.append(f"  • {t}")

        if self.review_notes:
            lines.extend(["", "Review Notes:"])
            for note in self.review_notes:
                lines.append(f"  ⚠ {note}")

        return "\n".join(lines)


class FixMode(str, Enum):
    PLAN = "PLAN"
    PATCH = "PATCH"
    AUTO = "AUTO"


@dataclass
class AutonomousFixResult:
    """
    Complete result of an autonomous code fix execution (v1.9).
    """
    mode: FixMode
    status: str  # 'success', 'plan_only', 'patch_only', 'failed', 'refused_dirty_tree', 'rolled_back'
    request: str
    phase: str  # 'analyze', 'plan', 'patch', 'validate', 'apply', 'test', 'review', 'complete', 'rollback'
    plan: Optional[CodeChangePlan] = None
    proposal: Optional[CodeChangeProposal] = None
    validation: Optional[PatchValidationResult] = None
    applied: bool = False
    test_result: Optional[TestValidationResult] = None
    review: Optional[GitChangeReview] = None
    rollback: Optional[RollbackResult] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value if isinstance(self.mode, FixMode) else str(self.mode),
            "status": self.status,
            "request": self.request,
            "phase": self.phase,
            "plan": self.plan.to_dict() if self.plan else None,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "applied": self.applied,
            "test_result": self.test_result.to_dict() if self.test_result else None,
            "review": self.review.to_dict() if self.review else None,
            "rollback": self.rollback.to_dict() if self.rollback else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "message": self.message,
        }

    def to_formatted_text(self) -> str:
        mode_val = self.mode.value if isinstance(self.mode, FixMode) else str(self.mode)
        lines = [
            "DevPilot v1.9 — Autonomous Code Fix",
            f"Mode:    {mode_val}",
            f"Status:  {self.status.upper()}",
            f"Request: {self.request}",
            "═" * 56,
        ]

        if self.message:
            lines.extend([f"Message: {self.message}", ""])

        if self.plan:
            lines.extend([
                "Plan Overview:",
                f"  Target: {self.plan.target_symbol or self.plan.target_file or 'Unknown'}",
                f"  Risk:   {self.plan.risk}",
                f"  Reason: {self.plan.reason}",
                f"  Affected Files ({len(self.plan.affected_files)}): {', '.join(self.plan.affected_files) if self.plan.affected_files else 'None'}",
                f"  Relevant Tests ({len(self.plan.relevant_tests)}): {', '.join(self.plan.relevant_tests[:4]) if self.plan.relevant_tests else 'None'}",
                "",
            ])

        if self.proposal:
            lines.extend([
                "Patch Proposal:",
                f"  Target: {self.proposal.target or 'Unknown'}",
                f"  Risk:   {self.proposal.risk or 'LOW'}",
                "",
                "Diff Summary:",
                self.proposal.patch or getattr(self.proposal, "patch_diff", ""),
                "",
            ])

        if self.validation:
            lines.extend([
                "Patch Validation:",
                f"  Valid: {self.validation.is_valid}",
                f"  Files Affected: {', '.join(self.validation.affected_files)}",
                f"  Lines: +{self.validation.lines_added} / -{self.validation.lines_deleted}",
                "",
            ])

        if self.test_result:
            lines.extend([
                "Test Validation:",
                f"  Success:   {self.test_result.is_success}",
                f"  Passed:    {self.test_result.passed}",
                f"  Failed:    {self.test_result.failed}",
                f"  Exit Code: {self.test_result.exit_code}",
                f"  Duration:  {self.test_result.execution_time:.2f}s",
                "",
            ])

        if self.review:
            lines.extend([
                "Post-Apply Intelligent Review:",
                f"  Changed Files:   {len(self.review.changed_files)}",
                f"  Changed Symbols: {len(self.review.changed_symbols)}",
                f"  Impact Radius:   {self.review.impact.total_affected_symbols} symbols",
                f"  Risk Level:      {self.review.risk.level} ({self.review.risk.score}/100)",
                "",
            ])

        if self.rollback:
            lines.extend([
                "Rollback Execution:",
                f"  Status: {self.rollback.status.upper()}",
                f"  Message: {self.rollback.message}",
                f"  Reverted Files: {', '.join(self.rollback.reverted_files) if self.rollback.reverted_files else 'None'}",
                "",
            ])

        if self.errors:
            lines.extend(["Errors:"])
            for e in self.errors:
                lines.append(f"  ❌ {e}")
            lines.append("")

        if self.warnings:
            lines.extend(["Warnings:"])
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
            lines.append("")

        if self.status == "success":
            lines.extend([
                "Result: Fix applied, tested, and verified successfully. Changes kept in working tree.",
            ])
        elif self.status == "rolled_back":
            lines.extend([
                "Result: Fix failed validation/tests. Repository changes were rolled back cleanly.",
            ])

        return "\n".join(lines).strip()


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATED = "VALIDATED"
    APPLIED = "APPLIED"
    TESTING = "TESTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ChangeExecution:
    """
    Complete structured record of executing an approved change proposal (v2.2).
    """
    proposal_id: str
    execution_id: Optional[str] = None
    status: str = "PENDING"
    mode: str = "APPROVED_EXECUTION"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    changed_files: List[str] = field(default_factory=list)
    test_result: Optional[TestValidationResult] = None
    validation_result: Optional[PatchValidationResult] = None
    error: Optional[str] = None
    rollback_status: Optional[str] = None
    checkpoint_id: Optional[str] = None
    diff: Optional[str] = None
    steps: Dict[str, str] = field(default_factory=lambda: {
        "pre_flight": "PENDING",
        "patch_validation": "PENDING",
        "patch_application": "PENDING",
        "tests": "PENDING",
        "repo_state": "PENDING",
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "proposal_id": self.proposal_id,
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "changed_files": self.changed_files,
            "test_result": self.test_result.to_dict() if self.test_result else None,
            "validation_result": self.validation_result.to_dict() if self.validation_result else None,
            "error": self.error,
            "rollback_status": self.rollback_status,
            "checkpoint_id": self.checkpoint_id,
            "diff": self.diff,
            "steps": self.steps,
        }

    def to_formatted_text(self) -> str:
        lines = [
            "DevPilot v2.2 — Change Execution",
            "────────────────────────────────",
            f"Proposal: {self.proposal_id}",
            "Status: APPROVED",
            f"Execution: {self.execution_id or 'unknown'}",
            "",
            f"Pre-flight: {self.steps.get('pre_flight', 'PENDING')}",
            f"Patch validation: {self.steps.get('patch_validation', 'PENDING')}",
            f"Patch application: {self.steps.get('patch_application', 'PENDING')}",
            f"Tests: {self.steps.get('tests', 'PENDING')}",
            f"Repository state: {self.steps.get('repo_state', 'PENDING')}",
            "",
            f"Execution Result: {self.status}",
        ]

        if self.rollback_status and self.rollback_status != "NONE":
            lines.append(f"Rollback: {self.rollback_status}")

        if self.error:
            lines.extend(["", f"Error: {self.error}"])

        if self.changed_files and self.status == "SUCCESS":
            lines.extend(["", f"Changed Files ({len(self.changed_files)}):"])
            for f in self.changed_files:
                lines.append(f"  • {f}")

        return "\n".join(lines)


@dataclass
class FailureAnalysis:
    """
    Structured diagnosis of test suite and execution failures (v2.3).
    """
    failed_tests: List[str] = field(default_factory=list)
    error_type: str = "UnknownError"
    error_message: str = ""
    traceback: str = ""
    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    likely_root_cause: str = ""
    confidence: float = 0.5
    suggested_fix_direction: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failed_tests": self.failed_tests,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "affected_files": self.affected_files,
            "affected_symbols": self.affected_symbols,
            "likely_root_cause": self.likely_root_cause,
            "confidence": self.confidence,
            "suggested_fix_direction": self.suggested_fix_direction,
        }


class FixIterationStatus(str, Enum):
    ANALYZING = "ANALYZING"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    TESTING = "TESTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class FixIteration:
    """
    Record of a single repair cycle in the autonomous fix loop (v2.3).
    """
    iteration_id: str
    iteration_number: int
    execution_id: Optional[str] = None
    proposal_id: Optional[str] = None
    status: str = "PROPOSED"
    failure_analysis: Optional[FailureAnalysis] = None
    proposed_fix_summary: str = ""
    patch: str = ""
    tests_before: Optional[Dict[str, Any]] = None
    tests_after: Optional[Dict[str, Any]] = None
    rollback_status: Optional[str] = None
    error: Optional[str] = None
    changed_files: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration_id": self.iteration_id,
            "iteration_number": self.iteration_number,
            "execution_id": self.execution_id,
            "proposal_id": self.proposal_id,
            "status": self.status,
            "failure_analysis": self.failure_analysis.to_dict() if self.failure_analysis else None,
            "proposed_fix_summary": self.proposed_fix_summary,
            "patch": self.patch,
            "tests_before": self.tests_before,
            "tests_after": self.tests_after,
            "rollback_status": self.rollback_status,
            "error": self.error,
            "changed_files": self.changed_files,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class FixLoopResult:
    """
    Outcome of an end-to-end Git-aware autonomous fix loop session (v2.3).
    """
    loop_id: str
    request: str
    mode: str = "plan"
    target: str = ""
    target_file: str = ""
    status: str = "SUCCESS"
    current_iteration: int = 1
    max_iterations: int = 3
    iterations: List[FixIteration] = field(default_factory=list)
    final_result: Optional[ChangeExecution] = None
    rollback_status: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    message: str = ""
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "request": self.request,
            "mode": self.mode,
            "target": self.target,
            "target_file": self.target_file,
            "status": self.status,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "iterations": [it.to_dict() for it in self.iterations],
            "final_result": self.final_result.to_dict() if self.final_result else None,
            "rollback_status": self.rollback_status,
            "errors": self.errors,
            "warnings": self.warnings,
            "message": self.message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def to_formatted_text(self) -> str:
        lines = [
            "DevPilot v2.3 — Autonomous Fix Loop",
            "────────────────────────────────────",
            "",
            "Request:",
            self.request,
            "",
            "Target:",
            self.target or self.target_file or "Unknown",
        ]

        if self.mode == "plan":
            lines.extend([
                "",
                "Mode: PLAN (Dry run — no files modified)",
                f"Status: {self.status}",
            ])
            if self.message:
                lines.extend(["", f"Message: {self.message}"])
            return "\n".join(lines)

        for it in self.iterations:
            lines.extend([
                "",
                "────────────────────────────────────",
                f"Iteration: {it.iteration_number}/{self.max_iterations}",
                "",
            ])
            if it.proposed_fix_summary:
                lines.extend([
                    "Proposal:",
                    it.proposed_fix_summary,
                    "",
                ])
            lines.extend([
                "Approval:",
                "APPROVED",
                "",
                "Execution:",
                it.status,
            ])
            if it.tests_after is not None:
                is_pass = it.tests_after.get("is_success", False) if isinstance(it.tests_after, dict) else getattr(it.tests_after, "is_success", False)
                lines.extend([
                    "",
                    "Tests:",
                    "PASS" if is_pass else "FAILED",
                ])
            if it.failure_analysis:
                fa = it.failure_analysis
                lines.extend([
                    "",
                    "Failure Analysis:",
                    f"{fa.error_type}: {fa.error_message}" if fa.error_message else fa.error_type,
                    "",
                    "Suggested Fix:",
                    fa.suggested_fix_direction or fa.likely_root_cause or "Refine patch implementation",
                ])

        lines.extend([
            "",
            "────────────────────────────────────",
            "Final Status:",
            self.status,
        ])

        if self.rollback_status and self.rollback_status != "NONE":
            lines.extend([
                "",
                "Rollback:",
                self.rollback_status,
            ])

        if self.errors:
            lines.extend(["", f"Reason:\n{self.errors[0]}"])
        elif self.message:
            lines.extend(["", f"Message:\n{self.message}"])

        return "\n".join(lines)




