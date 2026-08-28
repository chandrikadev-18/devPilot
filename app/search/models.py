"""
DevPilot Semantic Code Intelligence Models.

Data models for semantic and hybrid search results with AST and Graph annotations.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SemanticSymbolResult:
    """
    Represents a semantically retrieved symbol annotated with dependency relationships.
    """
    symbol: str
    file: str
    start_line: int
    end_line: int
    score: float
    reason: str = ""
    symbol_type: str = "function"
    parent_symbol: Optional[str] = None
    related_symbols: List[str] = field(default_factory=list)
    code_snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": round(self.score, 4),
            "reason": self.reason,
            "symbol_type": self.symbol_type,
            "parent_symbol": self.parent_symbol,
            "related_symbols": self.related_symbols,
        }


@dataclass
class SemanticSearchOutput:
    """
    Structured output of a semantic or hybrid code search operation.
    """
    query: str
    results: List[SemanticSymbolResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
        }

    def to_formatted_text(self) -> str:
        """Renders a clean human-readable summary for CLI and Agent prompts."""
        if not self.results:
            return f"No code found semantically matching query: '{self.query}'"

        lines = [
            f"Semantic Search Results for: '{self.query}'",
            f"Total Matches: {len(self.results)}",
            "",
        ]

        for idx, r in enumerate(self.results, 1):
            sym_display = f"{r.symbol}()" if r.symbol_type in ("function", "method") and not r.symbol.endswith(")") else r.symbol
            lines.append(f"{idx}. {sym_display}")
            lines.append(f"   File:     {r.file}:{r.start_line}-{r.end_line}")
            lines.append(f"   Score:    {r.score:.2f}")
            if r.reason:
                lines.append(f"   Reason:   {r.reason}")
            if r.related_symbols:
                lines.append(f"   Related:  {', '.join(r.related_symbols[:5])}")
            lines.append("")

        return "\n".join(lines).strip()
