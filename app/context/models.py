"""
DevPilot Repository Intelligence & Context Engine Data Models.

Defines structured containers for symbols, source snippets, graph relationships,
related tests, and Git history assembled by the ContextEngine.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SymbolContext:
    """Detailed definition metadata for a symbol discovered in the repository."""
    name: str
    file_path: str
    symbol_type: Optional[str] = None
    parent_symbol: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SourceSnippet:
    """Targeted source code excerpt retrieved for context."""
    file_path: str
    start_line: int
    end_line: int
    code: str
    symbol_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RelatedTest:
    """Test file or test function identified as covering a symbol or module."""
    test_file: str
    test_function: Optional[str] = None
    line_number: Optional[int] = None
    reason: str = "matches target symbol"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class GitChangeContext:
    """Git commit or history metadata relevant to the target context."""
    commit_hash: str
    short_hash: str
    author: str
    date: str
    message: str
    files_changed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepositoryContext:
    """
    Comprehensive repository intelligence and context payload.
    Combines AST definitions, source snippets, dependency graph queries,
    related test discovery, and Git change history.
    """
    question: str
    target_symbol: Optional[str] = None
    target_file: Optional[str] = None
    symbols: List[SymbolContext] = field(default_factory=list)
    source_snippets: List[SourceSnippet] = field(default_factory=list)
    callers: List[Dict[str, Any]] = field(default_factory=list)
    callees: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[Dict[str, Any]] = field(default_factory=list)
    dependents: List[Dict[str, Any]] = field(default_factory=list)
    impact: Optional[Dict[str, Any]] = None
    impacted_files: List[str] = field(default_factory=list)
    related_tests: List[RelatedTest] = field(default_factory=list)
    git_history: List[GitChangeContext] = field(default_factory=list)
    recent_changes: List[GitChangeContext] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts RepositoryContext to a clean JSON-serializable dictionary."""
        return {
            "question": self.question,
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "symbols": [s.to_dict() for s in self.symbols],
            "source_snippets": [s.to_dict() for s in self.source_snippets],
            "callers": self.callers,
            "callees": self.callees,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "impact": self.impact,
            "impacted_files": self.impacted_files,
            "related_tests": [t.to_dict() for t in self.related_tests],
            "git_history": [g.to_dict() for g in self.git_history],
            "recent_changes": [g.to_dict() for g in self.recent_changes],
            "summary": self.summary,
        }

    def to_formatted_text(self) -> str:
        """
        Formats repository intelligence into a structured, concise context block
        for LLM prompt reasoning and agent explanation.
        """
        sections: List[str] = [f"=== REPOSITORY CONTEXT: {self.question} ==="]

        if self.target_symbol:
            sections.append(f"Target Symbol: {self.target_symbol}")
        if self.target_file:
            sections.append(f"Target File: {self.target_file}")

        # 1. Symbols & Source
        if self.symbols:
            sections.append("\n--- SYMBOL DEFINITIONS ---")
            for sym in self.symbols:
                loc = f"{sym.file_path}:{sym.start_line}-{sym.end_line}" if sym.start_line else sym.file_path
                parent_str = f" (in {sym.parent_symbol})" if sym.parent_symbol else ""
                sections.append(f"• {sym.name}{parent_str} [{sym.symbol_type or 'symbol'}] at {loc}")

        if self.source_snippets:
            sections.append("\n--- SOURCE SNIPPETS ---")
            for snip in self.source_snippets:
                header = f"[{snip.file_path}:{snip.start_line}-{snip.end_line}]"
                if snip.symbol_name:
                    header += f" ({snip.symbol_name})"
                sections.append(f"{header}\n{snip.code}")

        # 2. Graph Relationships
        if self.callers:
            sections.append(f"\n--- CALLERS ({len(self.callers)}) ---")
            for c in self.callers:
                sections.append(f"• {c.get('name', 'unknown')} in {c.get('file_path', '')}:{c.get('start_line', '')}")

        if self.callees:
            sections.append(f"\n--- CALLEES ({len(self.callees)}) ---")
            for c in self.callees:
                sections.append(f"• {c.get('name', 'unknown')} in {c.get('file_path', '')}:{c.get('start_line', '')}")

        if self.dependencies:
            sections.append(f"\n--- DEPENDENCIES ({len(self.dependencies)}) ---")
            for d in self.dependencies:
                depth_str = f" [depth {d.get('depth', 1)}]" if 'depth' in d else ""
                sections.append(f"• {d.get('name', 'unknown')} in {d.get('file_path', '')}{depth_str}")

        if self.dependents:
            sections.append(f"\n--- DEPENDENTS ({len(self.dependents)}) ---")
            for d in self.dependents:
                depth_str = f" [depth {d.get('depth', 1)}]" if 'depth' in d else ""
                sections.append(f"• {d.get('name', 'unknown')} in {d.get('file_path', '')}{depth_str}")

        if self.impact and self.impacted_files:
            sections.append(f"\n--- IMPACT ANALYSIS ({len(self.impacted_files)} files affected) ---")
            sections.append(f"Impacted Files: {', '.join(self.impacted_files)}")

        # 3. Related Tests
        if self.related_tests:
            sections.append(f"\n--- RELATED TESTS ({len(self.related_tests)}) ---")
            for t in self.related_tests:
                fn_str = f"::{t.test_function}" if t.test_function else ""
                sections.append(f"• {t.test_file}{fn_str} ({t.reason})")

        # 4. Git History
        if self.git_history:
            sections.append(f"\n--- GIT HISTORY ({len(self.git_history)} commits) ---")
            for g in self.git_history:
                sections.append(f"• [{g.short_hash}] {g.date} by {g.author}: {g.message}")

        if self.recent_changes and not self.git_history:
            sections.append(f"\n--- RECENT COMMITS ({len(self.recent_changes)}) ---")
            for g in self.recent_changes:
                sections.append(f"• [{g.short_hash}] {g.date} by {g.author}: {g.message}")

        return "\n".join(sections)
