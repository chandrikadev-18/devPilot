"""
DevPilot Git-Aware Change Intelligence Service (v2.0).

Analyzes the actual uncommitted Git working tree (staged, unstaged, untracked)
to identify changed files, modified AST symbols, dependency blast radius,
relevant test suites, and deterministic risk assessment.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.changes.detector import _extract_symbols_map
from app.changes.models import ChangedSymbol, ChangeImpact, ChangeRisk, RiskLevel, SymbolChangeType
from app.changes.risk import calculate_change_risk
from app.git.change_detector import GitChangeDetector
from app.git.models import ChangeSummary, ChangeType, GitChange
from app.git.repository import (
    GitError,
    GitRepository,
    NotAGitRepositoryError,
    get_repository,
    is_git_repository,
)
from app.graph.models import NodeType
from app.graph.queries import get_impact
from app.graph.store import GraphStore
from app.parser.python_parser import PythonParser


class GitChangeIntelligenceService:
    """
    Read-only service for analyzing uncommitted Git changes and mapping them
    to codebase symbols, dependency graph impacts, test suites, and risk levels.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.detector = GitChangeDetector(project_root=self.project_root)

    def analyze_working_tree(
        self,
        graph: Optional[GraphStore] = None,
    ) -> ChangeSummary:
        """
        Performs full read-only Git working tree change intelligence analysis.
        """
        # 1. Verify Git repository
        if not is_git_repository(self.project_root):
            raise NotAGitRepositoryError(f"Directory '{self.project_root}' is not a Git repository.")

        repo = get_repository(self.project_root)
        raw = repo.raw_repo
        warnings: List[str] = []

        # 2. Get Branch and Git Changes
        try:
            branch = self.detector.get_current_branch()
        except Exception as e:
            branch = "HEAD"
            warnings.append(f"Unable to determine current branch: {e}")

        try:
            changes = self.detector.get_changes()
        except Exception as e:
            raise GitError(f"Error inspecting working tree changes: {e}") from e

        # If working tree is completely clean
        if not changes:
            return ChangeSummary(
                branch=branch,
                current_branch=branch,
                changed_files=[],
                changed_symbols=[],
                impacted_symbols=[],
                impacted_files=[],
                relevant_tests=[],
                risk="LOW",
                risk_reason="No uncommitted changes detected in working tree.",
                warnings=warnings,
                recommendation="Working tree is clean. Ready for development or commit.",
                direct_impact_count=0,
                indirect_impact_count=0,
                impacted_files_count=0,
            )

        # 3. Detect Changed Symbols across Python Files
        parser = PythonParser()
        changed_symbols_list: List[str] = []
        changed_symbols_objects: List[ChangedSymbol] = []
        seen_sym_keys: Set[str] = set()

        head_commit = raw.head.commit if raw.head.is_valid() else None

        for cf in changes:
            fpath = cf.file_path
            if not fpath.endswith(".py"):
                continue

            target_path = self.project_root / fpath

            # Read baseline from HEAD
            head_content = ""
            head_exists = False
            if head_commit is not None:
                try:
                    blob = head_commit.tree / fpath
                    head_content = blob.data_stream.read().decode("utf-8", errors="replace")
                    head_exists = True
                except Exception:
                    head_exists = False

            # Read current working tree file
            curr_content = ""
            curr_exists = False
            if target_path.exists() and target_path.is_file():
                try:
                    with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                        curr_content = f.read()
                    curr_exists = True
                except Exception as e:
                    warnings.append(f"Unable to read working tree file '{fpath}': {e}")
                    curr_exists = False

            # Check syntax validity of working tree content
            if curr_exists:
                try:
                    compile(curr_content, fpath, "exec")
                except SyntaxError as se:
                    warnings.append(f"Syntax error in working tree file '{fpath}': {se}")

            # Case A: Deleted file
            if head_exists and not curr_exists:
                try:
                    parsed_head = parser.parse_code(head_content.encode("utf-8"), fpath)
                    syms_head = _extract_symbols_map(parsed_head, fpath)
                    for sym_name, sym_info in syms_head.items():
                        if sym_name not in seen_sym_keys:
                            seen_sym_keys.add(sym_name)
                            changed_symbols_list.append(sym_name)
                            changed_symbols_objects.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=fpath,
                                    change_type=SymbolChangeType.DELETED.value,
                                    symbol_type=sym_info["type"],
                                    line_start=sym_info["start_line"],
                                    line_end=sym_info["end_line"],
                                )
                            )
                except Exception as e:
                    warnings.append(f"Error parsing baseline of deleted file '{fpath}': {e}")
                continue

            # Case B: Added / Untracked file
            if not head_exists and curr_exists:
                try:
                    parsed_curr = parser.parse_code(curr_content.encode("utf-8"), fpath)
                    syms_curr = _extract_symbols_map(parsed_curr, fpath)
                    for sym_name, sym_info in syms_curr.items():
                        if sym_name not in seen_sym_keys:
                            seen_sym_keys.add(sym_name)
                            changed_symbols_list.append(sym_name)
                            changed_symbols_objects.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=fpath,
                                    change_type=SymbolChangeType.ADDED.value,
                                    symbol_type=sym_info["type"],
                                    line_start=sym_info["start_line"],
                                    line_end=sym_info["end_line"],
                                )
                            )
                except Exception as e:
                    warnings.append(f"Syntax or parsing error in added file '{fpath}': {e}")
                continue

            # Case C: Modified file
            if head_exists and curr_exists:
                syms_head: Dict[str, dict] = {}
                syms_curr: Dict[str, dict] = {}

                try:
                    parsed_head = parser.parse_code(head_content.encode("utf-8"), fpath)
                    syms_head = _extract_symbols_map(parsed_head, fpath)
                except Exception as e:
                    warnings.append(f"Error parsing baseline of modified file '{fpath}': {e}")

                try:
                    parsed_curr = parser.parse_code(curr_content.encode("utf-8"), fpath)
                    syms_curr = _extract_symbols_map(parsed_curr, fpath)
                except Exception as e:
                    warnings.append(f"Syntax or parsing error in modified file '{fpath}': {e}")
                    # If current file has syntax error, record warning and continue
                    continue

                # Check added symbols in file
                for sym_name, sym_b in syms_curr.items():
                    if sym_name not in syms_head:
                        if sym_name not in seen_sym_keys:
                            seen_sym_keys.add(sym_name)
                            changed_symbols_list.append(sym_name)
                            changed_symbols_objects.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=fpath,
                                    change_type=SymbolChangeType.ADDED.value,
                                    symbol_type=sym_b["type"],
                                    line_start=sym_b["start_line"],
                                    line_end=sym_b["end_line"],
                                )
                            )
                    else:
                        # Modified symbol check
                        sym_a = syms_head[sym_name]
                        if sym_a["source"] != sym_b["source"] or sym_a["start_line"] != sym_b["start_line"]:
                            if sym_name not in seen_sym_keys:
                                seen_sym_keys.add(sym_name)
                                changed_symbols_list.append(sym_name)
                                changed_symbols_objects.append(
                                    ChangedSymbol(
                                        name=sym_name,
                                        file=fpath,
                                        change_type=SymbolChangeType.MODIFIED.value,
                                        symbol_type=sym_b["type"],
                                        line_start=sym_b["start_line"],
                                        line_end=sym_b["end_line"],
                                    )
                                )

                # Check deleted symbols in file
                for sym_name, sym_a in syms_head.items():
                    if sym_name not in syms_curr:
                        if sym_name not in seen_sym_keys:
                            seen_sym_keys.add(sym_name)
                            changed_symbols_list.append(sym_name)
                            changed_symbols_objects.append(
                                ChangedSymbol(
                                    name=sym_name,
                                    file=fpath,
                                    change_type=SymbolChangeType.DELETED.value,
                                    symbol_type=sym_a["type"],
                                    line_start=sym_a["start_line"],
                                    line_end=sym_a["end_line"],
                                )
                            )

        # 4. Impact Analysis via Dependency Graph
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        direct_impact_set: Set[str] = set()
        indirect_impact_set: Set[str] = set()
        impacted_files_set: Set[str] = set()
        relevant_tests_set: Set[str] = set()

        if active_graph and changed_symbols_list:
            for s_name in changed_symbols_list:
                cand_lookups = [s_name]
                if "." in s_name:
                    cand_lookups.append(s_name.split(".")[-1])

                for lookup in cand_lookups:
                    try:
                        impact_res = get_impact(active_graph, symbol=lookup, depth=2)
                        if impact_res and isinstance(impact_res, dict):
                            d_list = impact_res.get("direct_dependents") or impact_res.get("direct_callers") or []
                            for d in d_list:
                                d_name = d.get("name") if isinstance(d, dict) else getattr(d, "name", str(d))
                                d_file = d.get("file_path") if isinstance(d, dict) else getattr(d, "file_path", None)
                                d_file_str = str(d_file).replace("\\", "/") if d_file else ""

                                if "test" in d_file_str.lower() or d_name.lower().startswith("test_"):
                                    relevant_tests_set.add(d_file_str if d_file_str else d_name)
                                else:
                                    direct_impact_set.add(d_name)
                                    if d_file_str:
                                        impacted_files_set.add(d_file_str)

                            ind_list = impact_res.get("indirect_dependents") or impact_res.get("indirect_callers") or []
                            for ind in ind_list:
                                ind_name = ind.get("name") if isinstance(ind, dict) else getattr(ind, "name", str(ind))
                                ind_file = ind.get("file_path") if isinstance(ind, dict) else getattr(ind, "file_path", None)
                                ind_file_str = str(ind_file).replace("\\", "/") if ind_file else ""

                                if "test" in ind_file_str.lower() or ind_name.lower().startswith("test_"):
                                    relevant_tests_set.add(ind_file_str if ind_file_str else ind_name)
                                else:
                                    if ind_name not in direct_impact_set:
                                        indirect_impact_set.add(ind_name)
                                    if ind_file_str:
                                        impacted_files_set.add(ind_file_str)

                            for f in impact_res.get("impacted_files", []):
                                f_str = str(f).replace("\\", "/")
                                if "test" in f_str.lower():
                                    relevant_tests_set.add(f_str)
                                else:
                                    impacted_files_set.add(f_str)

                            if d_list or ind_list:
                                break
                    except Exception:
                        pass

        # 5. Test Intelligence
        changed_file_paths = [cf.file_path for cf in changes]
        tests_dir = self.project_root / "tests"

        # Direct test mapping from modified files
        for f in changed_file_paths:
            if f.startswith("tests/") and f.endswith(".py"):
                relevant_tests_set.add(f)
                continue

            stem = Path(f).stem
            parent_name = Path(f).parent.name
            candidates = [
                f"tests/test_{stem}.py",
                f"tests/test_{parent_name}_{stem}.py",
                f"tests/test_{stem.replace('_', '')}.py",
            ]
            for cand in candidates:
                if (self.project_root / cand).exists():
                    relevant_tests_set.add(cand)

        # Direct test mapping from impacted files
        for imp_f in impacted_files_set:
            imp_stem = Path(imp_f).stem
            cand = f"tests/test_{imp_stem}.py"
            if (self.project_root / cand).exists():
                relevant_tests_set.add(cand)

        # Match tests mentioning changed symbols in tests/ folder
        if tests_dir.exists() and tests_dir.is_dir() and changed_symbols_list:
            for s_name in changed_symbols_list:
                s_short = s_name.split(".")[-1].lower()
                for test_file in tests_dir.rglob("test_*.py"):
                    t_stem = test_file.stem.lower()
                    if s_short in t_stem:
                        rel_test = str(test_file.relative_to(self.project_root)).replace("\\", "/")
                        relevant_tests_set.add(rel_test)

        # Build sorted list
        all_impacted_symbols = sorted(list(direct_impact_set | indirect_impact_set))
        all_impacted_files = sorted(list(impacted_files_set))
        all_relevant_tests = sorted(list(relevant_tests_set))

        # 6. Risk Assessment
        direct_count = len(direct_impact_set)
        indirect_count = len(indirect_impact_set)
        total_impacted = direct_count + indirect_count
        impacted_file_count = len(all_impacted_files)
        changed_files_count = len(changes)

        # Deterministic Risk Categorization
        reasons_list: List[str] = []
        is_core_changed = any(
            "builder" in cf.file_path.lower()
            or "store" in cf.file_path.lower()
            or "main" in cf.file_path.lower()
            or "llm" in cf.file_path.lower()
            or "qdrant" in cf.file_path.lower()
            for cf in changes
        )

        if total_impacted > 15 or impacted_file_count > 4 or (is_core_changed and total_impacted > 5):
            risk_level = "HIGH"
        elif total_impacted > 3 or impacted_file_count > 1 or changed_files_count > 3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        if is_core_changed:
            reasons_list.append("Core shared module/infrastructure modified.")
        if direct_count > 0:
            reasons_list.append(f"{direct_count} direct dependent(s) affected.")
        if indirect_count > 0:
            reasons_list.append(f"{indirect_count} indirect dependent(s) affected.")
        if impacted_file_count > 0:
            reasons_list.append(f"{impacted_file_count} dependent file(s) affected.")
        if not all_relevant_tests and any(not cf.file_path.startswith("tests/") for cf in changes):
            reasons_list.append("No automated test callers identified for modified code.")
        elif all_relevant_tests:
            reasons_list.append(f"{len(all_relevant_tests)} relevant test suite(s) identified for validation.")

        if not reasons_list:
            reasons_list.append(f"Localized changes across {changed_files_count} file(s).")

        risk_reason_str = "\n".join(reasons_list)

        # Recommendation
        if risk_level == "HIGH":
            recommendation = "Run the affected graph, agent, and core test suites before committing."
        elif risk_level == "MEDIUM":
            recommendation = "Execute the recommended unit tests covering modified components before committing."
        else:
            recommendation = "Review changes and run local unit tests before committing."

        return ChangeSummary(
            branch=branch,
            current_branch=branch,
            changed_files=changes,
            changed_symbols=sorted(changed_symbols_list),
            impacted_symbols=all_impacted_symbols,
            impacted_files=all_impacted_files,
            relevant_tests=all_relevant_tests,
            risk=risk_level,
            risk_reason=risk_reason_str,
            warnings=warnings,
            recommendation=recommendation,
            direct_impact_count=direct_count,
            indirect_impact_count=indirect_count,
            impacted_files_count=impacted_file_count,
        )
