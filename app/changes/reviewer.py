"""
DevPilot Git-Aware Change Reviewer (v1.8).

Inspects working tree status, diffs, changed AST symbols, dependency graph impacts,
recommends relevant test suites, and deterministically evaluates change risk.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import git

from app.changes.detector import _extract_symbols_map
from app.changes.models import (
    ChangedSymbol,
    ChangeImpact,
    ChangeRisk,
    GitChangeReview,
    GitStatusSummary,
    RiskLevel,
    SymbolChangeType,
    TestRecommendation,
)
from app.changes.risk import calculate_change_risk
from app.git.repository import GitError, GitRepository, NotAGitRepositoryError, get_repository, is_git_repository
from app.graph.models import NodeType
from app.graph.queries import get_impact
from app.graph.store import GraphStore
from app.parser.python_parser import PythonParser


class GitChangeReviewer:
    """
    Read-only service that analyzes local Git working tree changes,
    extracts modified AST symbols, evaluates blast radius impact,
    discovers relevant tests, and scores risk.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def get_status_summary(self, repo: GitRepository) -> GitStatusSummary:
        """
        Inspects working tree and returns structured GitStatusSummary.
        """
        raw = repo.raw_repo

        # Determine current branch
        try:
            branch = raw.active_branch.name
        except TypeError:
            # Detached HEAD
            branch = f"HEAD ({raw.head.commit.hexsha[:7]})" if raw.head.is_valid() else "HEAD"
        except Exception:
            branch = "HEAD"

        # Determine base/tracking branch
        base_branch: Optional[str] = None
        ahead = 0
        behind = 0
        try:
            tracking = raw.active_branch.tracking_branch()
            if tracking:
                base_branch = tracking.name
                # Calculate ahead/behind
                ahead = len(list(raw.iter_commits(f"{tracking.name}..{raw.active_branch.name}")))
                behind = len(list(raw.iter_commits(f"{raw.active_branch.name}..{tracking.name}")))
        except Exception:
            pass

        if not base_branch:
            # Fallback to origin/main or origin/master if they exist in remotes
            for cand in ["origin/main", "origin/master", "main", "master"]:
                try:
                    if cand in [r.name for r in raw.refs]:
                        base_branch = cand
                        break
                except Exception:
                    pass

        # Diff against index (unstaged changes)
        unstaged_diffs = raw.index.diff(None)
        unstaged_files = sorted(list({(d.a_path or d.b_path or "").replace("\\", "/") for d in unstaged_diffs if (d.a_path or d.b_path)}))

        # Diff against HEAD (staged changes)
        staged_files: List[str] = []
        if raw.head.is_valid():
            try:
                staged_diffs = raw.index.diff("HEAD")
                staged_files = sorted(list({(d.a_path or d.b_path or "").replace("\\", "/") for d in staged_diffs if (d.a_path or d.b_path)}))
            except Exception:
                staged_diffs = []
        else:
            staged_diffs = []

        # Untracked files
        untracked = sorted([u.replace("\\", "/") for u in raw.untracked_files])

        # Categorize changes
        modified_set: Set[str] = set()
        added_set: Set[str] = set()
        deleted_set: Set[str] = set()
        renamed_set: Set[str] = set()

        all_diff_items = list(unstaged_diffs) + list(staged_diffs)
        for d in all_diff_items:
            path = (d.b_path or d.a_path or "").replace("\\", "/")
            if not path:
                continue
            if d.new_file:
                added_set.add(path)
            elif d.deleted_file:
                deleted_set.add(path)
            elif getattr(d, "renamed_file", False) or (d.a_path and d.b_path and d.a_path != d.b_path):
                renamed_set.add(path)
            else:
                modified_set.add(path)

        is_clean = not (modified_set or added_set or deleted_set or renamed_set or untracked or staged_files or unstaged_files)

        return GitStatusSummary(
            branch=branch,
            base_branch=base_branch,
            is_clean=is_clean,
            modified_files=sorted(list(modified_set)),
            added_files=sorted(list(added_set)),
            deleted_files=sorted(list(deleted_set)),
            renamed_files=sorted(list(renamed_set)),
            untracked_files=untracked,
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            ahead_commits=ahead,
            behind_commits=behind,
        )

    def detect_working_tree_symbols(
        self,
        repo: GitRepository,
        status: GitStatusSummary,
    ) -> Tuple[List[str], List[ChangedSymbol], Dict[str, int], str]:
        """
        Extracts changed AST symbols from modified/added/deleted files and calculates diff line stats.
        """
        raw = repo.raw_repo
        parser = PythonParser()
        changed_symbols: List[ChangedSymbol] = []
        seen_keys: Set[str] = set()
        additions = 0
        deletions = 0
        diff_lines_list: List[str] = []

        all_candidate_files = sorted(
            list(
                set(status.modified_files)
                | set(status.added_files)
                | set(status.deleted_files)
                | set(status.renamed_files)
                | set(status.unstaged_files)
                | set(status.staged_files)
                | set(status.untracked_files)
            )
        )

        head_commit = raw.head.commit if raw.head.is_valid() else None

        for f_rel in all_candidate_files:
            if not f_rel.endswith(".py"):
                continue

            target_path = self.project_root / f_rel

            # 1. Read HEAD blob (baseline)
            head_content = ""
            head_exists = False
            if head_commit is not None:
                try:
                    blob = head_commit.tree / f_rel
                    head_content = blob.data_stream.read().decode("utf-8", errors="replace")
                    head_exists = True
                except Exception:
                    head_exists = False

            # 2. Read Working Tree content (current)
            curr_content = ""
            curr_exists = False
            if target_path.exists() and target_path.is_file():
                try:
                    with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                        curr_content = f.read()
                    curr_exists = True
                except Exception:
                    curr_exists = False

            # If file was deleted in working tree
            if head_exists and not curr_exists:
                parsed_head = parser.parse_code(head_content.encode("utf-8"), f_rel)
                syms_head = _extract_symbols_map(parsed_head, f_rel)
                for sym_name, sym_info in syms_head.items():
                    k = f"{f_rel}:{sym_name}"
                    if k not in seen_keys:
                        seen_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=f_rel,
                                change_type=SymbolChangeType.DELETED.value,
                                symbol_type=sym_info["type"],
                                line_start=sym_info["start_line"],
                                line_end=sym_info["end_line"],
                            )
                        )
                deletions += len(head_content.splitlines())
                continue

            # If file was added / untracked
            if not head_exists and curr_exists:
                parsed_curr = parser.parse_code(curr_content.encode("utf-8"), f_rel)
                syms_curr = _extract_symbols_map(parsed_curr, f_rel)
                for sym_name, sym_info in syms_curr.items():
                    k = f"{f_rel}:{sym_name}"
                    if k not in seen_keys:
                        seen_keys.add(k)
                        changed_symbols.append(
                            ChangedSymbol(
                                name=sym_name,
                                file=f_rel,
                                change_type=SymbolChangeType.ADDED.value,
                                symbol_type=sym_info["type"],
                                line_start=sym_info["start_line"],
                                line_end=sym_info["end_line"],
                            )
                        )
                additions += len(curr_content.splitlines())
                continue

            # If file was modified: compare ASTs
            if head_exists and curr_exists:
                parsed_head = parser.parse_code(head_content.encode("utf-8"), f_rel)
                parsed_curr = parser.parse_code(curr_content.encode("utf-8"), f_rel)
                syms_head = _extract_symbols_map(parsed_head, f_rel)
                syms_curr = _extract_symbols_map(parsed_curr, f_rel)

                # Check added symbols in modified file
                for sym_name, sym_b in syms_curr.items():
                    if sym_name not in syms_head:
                        k = f"{f_rel}:{sym_name}"
                        if k not in seen_keys:
                            seen_keys.add(k)
                            changed_symbols.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=f_rel,
                                    change_type=SymbolChangeType.ADDED.value,
                                    symbol_type=sym_b["type"],
                                    line_start=sym_b["start_line"],
                                    line_end=sym_b["end_line"],
                                )
                            )
                    else:
                        # In both: check if definition or body changed
                        sym_a = syms_head[sym_name]
                        if sym_a["source"] != sym_b["source"] or sym_a["start_line"] != sym_b["start_line"]:
                            k = f"{f_rel}:{sym_name}"
                            if k not in seen_keys:
                                seen_keys.add(k)
                                changed_symbols.append(
                                    ChangedSymbol(
                                        name=sym_name,
                                        file=f_rel,
                                        change_type=SymbolChangeType.MODIFIED.value,
                                        symbol_type=sym_b["type"],
                                        line_start=sym_b["start_line"],
                                        line_end=sym_b["end_line"],
                                    )
                                )

                # Check deleted symbols in modified file
                for sym_name, sym_a in syms_head.items():
                    if sym_name not in syms_curr:
                        k = f"{f_rel}:{sym_name}"
                        if k not in seen_keys:
                            seen_keys.add(k)
                            changed_symbols.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=f_rel,
                                    change_type=SymbolChangeType.DELETED.value,
                                    symbol_type=sym_a["type"],
                                    line_start=sym_a["start_line"],
                                    line_end=sym_a["end_line"],
                                )
                            )

        # Compute line diff metrics
        try:
            # Staged + unstaged diff summary
            staged_patch = raw.git.diff("HEAD") if raw.head.is_valid() else ""
            unstaged_patch = raw.git.diff()
            full_diff = staged_patch + ("\n" if staged_patch and unstaged_patch else "") + unstaged_patch

            if full_diff:
                for line in full_diff.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        additions += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        deletions += 1
        except Exception:
            full_diff = ""

        diff_stats = {"additions": additions, "deletions": deletions}
        return all_candidate_files, changed_symbols, diff_stats, full_diff

    def calculate_impact(
        self,
        changed_symbols: List[ChangedSymbol],
        graph: Optional[GraphStore] = None,
    ) -> ChangeImpact:
        """
        Calculates dependency graph blast radius across direct and indirect dependents.
        """
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        direct_set: Set[str] = set()
        indirect_set: Set[str] = set()
        impacted_files_set: Set[str] = set()

        if active_graph:
            for s in changed_symbols:
                cand_names = [s.name]
                if "." in s.name:
                    cand_names.append(s.name.split(".")[-1])

                for sym_lookup in cand_names:
                    try:
                        impact_res = get_impact(active_graph, symbol=sym_lookup, depth=2)
                        if impact_res and isinstance(impact_res, dict):
                            d_list = impact_res.get("direct_dependents") or impact_res.get("direct_callers") or []
                            for d in d_list:
                                d_name = d.get("name") if isinstance(d, dict) else getattr(d, "name", str(d))
                                d_file = d.get("file_path") if isinstance(d, dict) else getattr(d, "file_path", None)
                                direct_set.add(d_name)
                                if d_file:
                                    impacted_files_set.add(d_file)

                            ind_list = impact_res.get("indirect_dependents") or impact_res.get("indirect_callers") or []
                            for ind in ind_list:
                                ind_name = ind.get("name") if isinstance(ind, dict) else getattr(ind, "name", str(ind))
                                ind_file = ind.get("file_path") if isinstance(ind, dict) else getattr(ind, "file_path", None)
                                indirect_set.add(ind_name)
                                if ind_file:
                                    impacted_files_set.add(ind_file)

                            for f in impact_res.get("impacted_files", []):
                                impacted_files_set.add(f)

                            if d_list or ind_list:
                                break
                    except Exception:
                        pass

        return ChangeImpact(
            direct_dependents=sorted(direct_set),
            indirect_dependents=sorted(indirect_set - direct_set),
            impacted_files=sorted(impacted_files_set),
            total_affected_symbols=len(direct_set | indirect_set),
        )

    def discover_recommended_tests(
        self,
        changed_files: List[str],
        changed_symbols: List[ChangedSymbol],
        impact: ChangeImpact,
        graph: Optional[GraphStore] = None,
    ) -> Tuple[List[str], List[TestRecommendation]]:
        """
        Discovers relevant test suites and test functions based on changed files,
        symbols, and dependent caller relationships.
        """
        recommendations: List[TestRecommendation] = []
        rec_keys: Set[str] = set()
        simple_test_list: List[str] = []

        tests_dir = self.project_root / "tests"

        # 1. Direct file mapping (e.g. app/graph/builder.py -> tests/test_graph_builder.py, tests/test_builder.py)
        for f in changed_files:
            stem = Path(f).stem
            parent_dir = Path(f).parent.name
            candidates = [
                f"tests/test_{stem}.py",
                f"tests/test_{parent_dir}_{stem}.py",
                f"tests/test_{stem.replace('_', '')}.py",
            ]
            # If changing a test file directly
            if f.startswith("tests/") and f.endswith(".py"):
                if f not in rec_keys:
                    rec_keys.add(f)
                    recommendations.append(
                        TestRecommendation(
                            test_target=f,
                            file_path=f,
                            reason=f"Modified test suite: {f}",
                        )
                    )
                    simple_test_list.append(f)

            for cand in candidates:
                if (self.project_root / cand).exists() and cand not in rec_keys:
                    rec_keys.add(cand)
                    recommendations.append(
                        TestRecommendation(
                            test_target=cand,
                            file_path=cand,
                            reason=f"Direct test suite for modified file '{f}'",
                        )
                    )
                    simple_test_list.append(cand)

        # 2. Graph test callers of changed symbols
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        if active_graph:
            sym_names = {s.name for s in changed_symbols}
            for node in active_graph.get_nodes():
                # Check if this node is a test function/caller
                is_test_node = (
                    (node.file_path and node.file_path.startswith("tests/"))
                    or node.name.startswith("test_")
                )
                if not is_test_node:
                    continue

                # Check outgoing edges from this test node
                for edge in active_graph.get_outgoing_edges(node.id):
                    target_node = active_graph.get_node(edge.target_id)
                    if target_node:
                        p_cls = target_node.metadata.get("parent_class")
                        full_tname = f"{p_cls}.{target_node.name}" if p_cls else target_node.name

                        if target_node.name in sym_names or full_tname in sym_names:
                            loc = f"{node.file_path}:{node.start_line}" if node.start_line else (node.file_path or "")
                            t_target = f"{node.name} ({loc})" if loc else node.name
                            if t_target not in rec_keys:
                                rec_keys.add(t_target)
                                recommendations.append(
                                    TestRecommendation(
                                        test_target=t_target,
                                        file_path=node.file_path or "",
                                        symbol_name=node.name,
                                        reason=f"Directly tests changed symbol '{full_tname}'",
                                    )
                                )
                                simple_test_list.append(t_target)

        # 3. Add test suites for impacted files
        for imp_file in impact.impacted_files:
            imp_stem = Path(imp_file).stem
            cand = f"tests/test_{imp_stem}.py"
            if (self.project_root / cand).exists() and cand not in rec_keys:
                rec_keys.add(cand)
                recommendations.append(
                    TestRecommendation(
                        test_target=cand,
                        file_path=cand,
                        reason=f"Tests impacted dependent component in '{imp_file}'",
                    )
                )
                simple_test_list.append(cand)

        return sorted(list(set(simple_test_list))), recommendations

    def review_working_tree(
        self,
        graph: Optional[GraphStore] = None,
    ) -> GitChangeReview:
        """
        Performs full read-only intelligent Git change review.
        """
        if not is_git_repository(self.project_root):
            raise NotAGitRepositoryError(f"Directory '{self.project_root}' is not a Git repository.")

        repo = get_repository(self.project_root)

        # 1. Inspect Git Status
        status = self.get_status_summary(repo)

        # If completely clean
        if status.is_clean:
            risk = ChangeRisk(
                score=0,
                level=RiskLevel.LOW.value,
                reasons=["Clean repository: No uncommitted changes to review."],
            )
            return GitChangeReview(
                branch=status.branch,
                base_branch=status.base_branch,
                is_clean=True,
                status=status,
                changed_files=[],
                changed_symbols=[],
                impact=ChangeImpact(),
                risk=risk,
                recommended_tests=[],
                test_recommendations=[],
                diff_stats={"additions": 0, "deletions": 0},
                diff_summary="",
                review_notes=["Working tree is clean. No unstaged or staged modifications."],
                summary="Working tree is clean. No local modifications to review.",
            )

        # 2. Detect Changed Files & AST Symbols
        changed_files, changed_symbols, diff_stats, full_diff = self.detect_working_tree_symbols(repo, status)

        # Ensure untracked files are accounted for in changed_files
        all_changed_files = sorted(list(set(changed_files) | set(status.untracked_files)))

        # 3. Calculate Blast Radius Impact
        impact = self.calculate_impact(changed_symbols, graph=graph)

        # 4. Discover Recommended Tests
        rec_test_strings, rec_test_items = self.discover_recommended_tests(
            changed_files=all_changed_files,
            changed_symbols=changed_symbols,
            impact=impact,
            graph=graph,
        )

        # 5. Calculate Deterministic Risk Score
        risk = calculate_change_risk(
            changed_files=all_changed_files,
            changed_symbols=changed_symbols,
            impact=impact,
        )

        # Adjust risk if tests are missing for modified core files
        if not rec_test_strings and any(not f.startswith("tests/") for f in all_changed_files):
            risk.score = min(100, risk.score + 10)
            risk.reasons.append("No existing automated test suites identified for modified components.")

        # 6. Generate Review Notes & Narrative
        notes: List[str] = []
        if status.untracked_files:
            notes.append(f"{len(status.untracked_files)} untracked file(s) present in working tree.")
        if any(s.change_type == SymbolChangeType.DELETED.value for s in changed_symbols):
            notes.append("Potential breaking change: Symbol deletion detected.")
        if impact.direct_dependents:
            notes.append(f"Directly affects {len(impact.direct_dependents)} calling component(s).")
        if risk.level in ("HIGH", "CRITICAL"):
            notes.append("High blast radius across codebase. Validate with recommended tests before committing.")

        summary_lines = [
            f"Working tree has {len(all_changed_files)} changed file(s) ({diff_stats['additions']} additions, {diff_stats['deletions']} deletions).",
            f"Detected {len(changed_symbols)} altered AST symbol(s) with {impact.total_affected_symbols} total affected component(s).",
            f"Risk Level: {risk.level} ({risk.score}/100).",
        ]
        summary = " ".join(summary_lines)

        return GitChangeReview(
            branch=status.branch,
            base_branch=status.base_branch,
            is_clean=False,
            status=status,
            changed_files=all_changed_files,
            changed_symbols=changed_symbols,
            impact=impact,
            risk=risk,
            recommended_tests=rec_test_strings,
            test_recommendations=rec_test_items,
            diff_stats=diff_stats,
            diff_summary=full_diff[:2000] if full_diff else "",
            review_notes=notes,
            summary=summary,
        )
