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
