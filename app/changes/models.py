"""
DevPilot Code Change Intelligence Models.

Data models for symbol-level change detection, static dependency impact,
and deterministic risk evaluation.
"""

from dataclasses import dataclass, field
from enum import Enum
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
    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    relevant_tests: List[str] = field(default_factory=list)
    recommended_order: List[str] = field(default_factory=list)
    risk: str = "LOW"
    reason: str = ""
    evidence: List[ChangePlanEvidence] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)

    def to_formatted_string(self) -> str:
        """Renders the required DevPilot v1.7 change plan output format."""
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_request": self.change_request,
            "target": self.target_symbol or self.target_file or "Unknown",
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "target_lines": self.target_lines,
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


