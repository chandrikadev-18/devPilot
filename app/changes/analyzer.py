"""
DevPilot Code Change Analyzer.

Orchestrates Git commit inspection, changed symbol extraction,
dependency graph impact traversal, and risk evaluation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.changes.detector import detect_changed_symbols
from app.changes.models import ChangeImpact, ChangeRisk, CodeChangeAnalysis
from app.changes.risk import calculate_change_risk
from app.git.history import get_commit_detail
from app.git.repository import GitCommitNotFoundError, GitError, get_repository
from app.graph.queries import get_impact


class CodeChangeAnalyzer:
    """
    Analyzes code changes in Git commits, maps them to AST symbols,
    calculates static dependency graph impacts, and evaluates risk.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def analyze_commit(
        self,
        commit_hash: str = "HEAD",
        graph: Optional[Any] = None,
    ) -> CodeChangeAnalysis:
        """
        Runs comprehensive change analysis on a given Git commit hash or revision.
        """
        repo = get_repository(self.project_root)

        # 1. Retrieve commit details
        commit_detail = get_commit_detail(repo, commit_hash=commit_hash)

        # 2. Detect changed files and AST symbols
        changed_files, changed_symbols = detect_changed_symbols(
            repo=repo,
            commit_hash=commit_detail.commit_hash,
        )

        # Ensure changed_files contains at least the files reported by git commit stats
        if not changed_files and commit_detail.files_changed:
            changed_files = list(commit_detail.files_changed)

        # 3. Calculate Dependency Graph Impact
        active_graph = graph
        if active_graph is None:
            from app.agent.tools import _resolve_graph
            active_graph = _resolve_graph(None, self.project_root)

        direct_set: Set[str] = set()
        indirect_set: Set[str] = set()
        impacted_files_set: Set[str] = set()

        if active_graph:
            for s in changed_symbols:
                try:
                    # Query impact on the symbol name (e.g. GraphBuilder.build or build)
                    impact_res = get_impact(active_graph, symbol=s.name, max_depth=2)
                    if impact_res:
                        for d in impact_res.direct_dependents:
                            direct_set.add(d.name)
                            if d.file_path:
                                impacted_files_set.add(d.file_path)
                        for ind in impact_res.indirect_dependents:
                            indirect_set.add(ind.name)
                            if ind.file_path:
                                impacted_files_set.add(ind.file_path)
                        for f in impact_res.impacted_files:
                            impacted_files_set.add(f)
                except Exception:
                    pass

        impact = ChangeImpact(
            direct_dependents=sorted(direct_set),
            indirect_dependents=sorted(indirect_set - direct_set),
            impacted_files=sorted(impacted_files_set),
            total_affected_symbols=len(direct_set | indirect_set),
        )

        # 4. Calculate Deterministic Risk Score
        risk = calculate_change_risk(
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            impact=impact,
        )

        return CodeChangeAnalysis(
            commit=commit_detail.commit_hash,
            short_hash=commit_detail.short_hash,
            author=commit_detail.author_name,
            date=commit_detail.date,
            message=commit_detail.message,
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            impact=impact,
            risk=risk,
        )
