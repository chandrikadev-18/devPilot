"""
DevPilot Change Impact Planner.

Converts a developer change request into a grounded implementation plan
using the existing dependency graph, impact analysis, semantic search,
and evidence verification systems.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.changes.models import ChangePlanEvidence, CodeChangePlan
from app.changes.risk import calculate_plan_risk
from app.graph.models import NodeType
from app.graph.queries import get_dependents, get_impact
from app.search.hybrid_search import HybridCodeSearchEngine
from app.vector_store.qdrant_store import ValidationError


def _clean_request_candidate(raw: str) -> str:
    """Extracts candidate symbol or file from natural language change request."""
    cleaned = raw.strip().strip("'\"`?,.:;()[]{}")
    prefixes = [
        "improve ", "optimize ", "refactor ", "update ", "modify ", "fix ",
        "change ", "rewrite ", "enhance ", "add feature to ", "performance of ",
        "in ", "for ", "the ", "function ", "class ", "method ",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True

    suffixes = [
        " performance", " speed", " logic", " implementation", " function",
        " method", " class", " module", " behavior", " bug", " feature",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if cleaned.lower().endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
                changed = True

    return cleaned.strip().strip("'\"`?,.:;()[]{}")


class ChangeImpactPlanner:
    """
    Analyzes proposed code changes, determines affected symbols and files,
    discovers relevant tests, calculates risk, and constructs a grounded plan.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        low_risk_threshold: int = 5,
        medium_risk_threshold: int = 15,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.low_risk_threshold = low_risk_threshold
        self.medium_risk_threshold = medium_risk_threshold

    def plan_change(
        self,
        change_request: str,
        graph: Optional[Any] = None,
    ) -> CodeChangePlan:
        """
        Constructs a grounded CodeChangePlan for a given change request.
        """
        if not change_request or not change_request.strip():
            raise ValidationError("Change request cannot be empty.")

        q_clean = change_request.strip()

        # 1. Resolve Dependency Graph
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        # 2. Extract Candidate and Resolve Target Symbol / File
        target_symbol = ""
        target_file = ""
        target_lines: Optional[str] = None
        unverified: List[str] = []
        evidence: List[ChangePlanEvidence] = []

        # Check for direct .py file in request
        file_match = re.search(r"([a-zA-Z0-9_/\\.]+\.py)", q_clean)
        file_candidate = file_match.group(1).replace("\\", "/") if file_match else None

        # Candidate symbol token
        candidate_token = _clean_request_candidate(q_clean)

        resolved_node = None

        # Strategy 1: Explicit .py file in change request
        if file_candidate:
            target_file = file_candidate
            if active_graph:
                norm_fc = file_candidate.lower()
                for n in active_graph.get_nodes():
                    if n.file_path and (str(n.file_path).replace("\\", "/").lower() == norm_fc or str(n.file_path).replace("\\", "/").lower().endswith(norm_fc)):
                        p_cls = n.metadata.get("parent_class")
                        target_symbol = f"{p_cls}.{n.name}" if p_cls else n.name
                        resolved_node = n
                        break
            if not target_symbol:
                target_symbol = Path(file_candidate).stem

        # Strategy 2: Look up candidate symbol directly in graph store
        if not target_file and active_graph and candidate_token:
            from app.graph.queries import _resolve_target_nodes
            try:
                matched_nodes = _resolve_target_nodes(active_graph, candidate_token, allow_multiple=True)
                if matched_nodes:
                    resolved_node = matched_nodes[0]
            except Exception:
                pass

            if resolved_node is None:
                named_nodes = active_graph.find_nodes_by_name(candidate_token)
                if named_nodes:
                    resolved_node = named_nodes[0]

            if resolved_node is None:
                cand_lower = candidate_token.lower()
                for n in active_graph.get_nodes():
                    n_sym = n.name.lower()
                    p_cls = (n.metadata.get("parent_class") or "").lower()
                    if n_sym == cand_lower or (p_cls and f"{p_cls}.{n_sym}" == cand_lower):
                        resolved_node = n
                        break

        # Strategy 3: Look up via AST parser if graph didn't find exact node
        if not target_file and resolved_node is None and candidate_token:
            try:
                from app.agent.tools import create_find_symbol_tool
                find_tool = create_find_symbol_tool(project_root=self.project_root)
                find_res = find_tool["func"](candidate_token)
                data = find_res.get("data", [])
                if isinstance(data, list) and data:
                    match = data[0]
                    target_file = str(match.get("file_path", "")).replace("\\", "/")
                    p_sym = match.get("parent_symbol")
                    s_name = match.get("symbol_name", candidate_token)
                    target_symbol = f"{p_sym}.{s_name}" if p_sym else s_name
                    s_line = match.get("start_line", 1)
                    e_line = match.get("end_line", s_line)
                    target_lines = f"{s_line}-{e_line}"
            except Exception:
                pass

        if resolved_node is not None and not target_file:
            p_cls = resolved_node.metadata.get("parent_class")
            target_symbol = f"{p_cls}.{resolved_node.name}" if p_cls else resolved_node.name
            target_file = str(resolved_node.file_path).replace("\\", "/")
            if resolved_node.start_line and resolved_node.end_line:
                target_lines = f"{resolved_node.start_line}-{resolved_node.end_line}"
            elif resolved_node.start_line:
                target_lines = str(resolved_node.start_line)

        # Strategy 4: If target is still unresolved, try semantic search fallback
        if not target_symbol and not target_file:
            try:
                engine = HybridCodeSearchEngine(project_root=self.project_root, graph=active_graph)
                sem_res = engine.search(query=q_clean, top_k=3)
                if sem_res.results and sem_res.results[0].score >= 0.70:
                    first = sem_res.results[0]
                    target_symbol = first.symbol
                    target_file = str(first.file).replace("\\", "/")
                    target_lines = f"{first.start_line}-{first.end_line}"
            except Exception:
                pass

        # Check if target resolution succeeded
        if not target_file and not resolved_node:
            target_symbol = candidate_token or q_clean
            unverified.append("Target symbol or file could not be verified in the codebase")

        # 3. Add target evidence if verified
        if target_file:
            evidence.append(
                ChangePlanEvidence(
                    file=target_file,
                    symbol=target_symbol or target_file,
                    lines=target_lines or "1",
                    relationship="Target definition",
                )
            )

        # 4. Dependency Graph Impact & Caller Traversal
        direct_dependents: Set[str] = set()
        indirect_dependents: Set[str] = set()
        impacted_files_set: Set[str] = set()
        relevant_tests_set: Set[str] = set()

        def _process_impact_dict(impact_data: Dict[str, Any]):
            d_list = impact_data.get("direct_dependents", []) or impact_data.get("direct_callers", [])
            for d in d_list:
                d_name = d.get("name") if isinstance(d, dict) else getattr(d, "name", str(d))
                d_file = d.get("file_path", "") if isinstance(d, dict) else getattr(d, "file_path", "")
                d_file = str(d_file).replace("\\", "/") if d_file else ""
                d_line = str(d.get("start_line") or d.get("call_line") or 1) if isinstance(d, dict) else str(getattr(d, "start_line", None) or getattr(d, "call_line", None) or 1)

                if "test" in d_file.lower() or d_name.lower().startswith("test_") or d_name.lower().startswith("test"):
                    test_label = f"{d_name} ({d_file}:{d_line})" if d_file else d_name
                    relevant_tests_set.add(test_label)
                    evidence.append(
                        ChangePlanEvidence(
                            file=d_file or "tests",
                            symbol=d_name,
                            lines=d_line,
                            relationship="Test caller (tests)",
                        )
                    )
                else:
                    direct_dependents.add(d_name)
                    if d_file:
                        impacted_files_set.add(d_file)
                        evidence.append(
                            ChangePlanEvidence(
                                file=d_file,
                                symbol=d_name,
                                lines=d_line,
                                relationship="Direct caller (calls)",
                            )
                        )

            ind_list = impact_data.get("indirect_dependents", []) or impact_data.get("indirect_callers", [])
            for ind in ind_list:
                ind_name = ind.get("name") if isinstance(ind, dict) else getattr(ind, "name", str(ind))
                ind_file = ind.get("file_path", "") if isinstance(ind, dict) else getattr(ind, "file_path", "")
                ind_file = str(ind_file).replace("\\", "/") if ind_file else ""
                ind_line = str(ind.get("start_line") or ind.get("call_line") or 1) if isinstance(ind, dict) else str(getattr(ind, "start_line", None) or getattr(ind, "call_line", None) or 1)

                if "test" in ind_file.lower() or ind_name.lower().startswith("test_"):
                    relevant_tests_set.add(f"{ind_name} ({ind_file}:{ind_line})" if ind_file else ind_name)
                else:
                    if ind_name not in direct_dependents:
                        indirect_dependents.add(ind_name)
                    if ind_file:
                        impacted_files_set.add(ind_file)

            for f in impact_data.get("impacted_files", []):
                f_clean = str(f).replace("\\", "/")
                if "test" not in f_clean.lower():
                    impacted_files_set.add(f_clean)

        if active_graph and target_symbol:
            try:
                impact_res = get_impact(active_graph, symbol=target_symbol, depth=3)
                if isinstance(impact_res, dict):
                    _process_impact_dict(impact_res)
            except Exception:
                pass

        # If target was file-based and direct_dependents is empty, aggregate from nodes in file
        if active_graph and target_file and not direct_dependents:
            file_norm = str(target_file).replace("\\", "/")
            file_nodes = [
                n for n in active_graph.get_nodes()
                if n.file_path and (str(n.file_path).replace("\\", "/") == file_norm or str(n.file_path).replace("\\", "/").endswith(file_norm))
            ]
            for fn in file_nodes:
                if fn.node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                    p_name = fn.metadata.get("parent_class")
                    fn_sym = f"{p_name}.{fn.name}" if p_name else fn.name
                    try:
                        fn_impact = get_impact(active_graph, symbol=fn_sym, depth=2)
                        if isinstance(fn_impact, dict):
                            _process_impact_dict(fn_impact)
                    except Exception:
                        pass

        # Also discover relevant test files by target module name matching in tests/
        target_mod_name = Path(target_file).stem.lower() if target_file else ""
        if target_mod_name and target_mod_name not in ("__init__", ""):
            tests_dir = self.project_root / "tests"
            if tests_dir.exists() and tests_dir.is_dir():
                for test_file in tests_dir.rglob("test_*.py"):
                    t_stem = test_file.stem.lower()
                    if target_mod_name in t_stem or (target_symbol and target_symbol.lower() in t_stem):
                        rel_p = str(test_file.relative_to(self.project_root)).replace("\\", "/")
                        relevant_tests_set.add(rel_p)

        # Build list of affected symbols and files
        affected_symbols_list = sorted(direct_dependents | indirect_dependents)
        if target_file:
            impacted_files_set.add(target_file)
        affected_files_list = sorted(impacted_files_set)
        relevant_tests_list = sorted(relevant_tests_set)

        # 5. Calculate Risk Score
        total_affected = len(affected_symbols_list)
        risk = calculate_plan_risk(
            total_affected_symbols=total_affected,
            low_threshold=self.low_risk_threshold,
            medium_threshold=self.medium_risk_threshold,
        )

        # Generate Grounded Reason
        reason_parts = []
        if target_symbol:
            reason_parts.append(
                f"Target '{target_symbol}' has {len(direct_dependents)} direct dependent(s) "
                f"and {len(indirect_dependents)} indirect dependent(s) across {len(affected_files_list)} file(s)."
            )
        if relevant_tests_list:
            reason_parts.append(f"{len(relevant_tests_list)} relevant test suite(s) identified for validation.")
        else:
            reason_parts.append("No automated test callers were identified in the static graph.")

        if risk == "HIGH":
            reason_parts.append("High blast radius across the codebase requires careful regression testing.")
        elif risk == "MEDIUM":
            reason_parts.append("Moderate blast radius requires verifying dependent modules.")
        else:
            reason_parts.append("Low blast radius makes this a localized, safe change.")

        reason = " ".join(reason_parts)

        # 6. Construct Recommended Implementation Order
        recommended_order: List[str] = []
        loc_str = f" in {target_file}:{target_lines}" if (target_file and target_lines) else (f" in {target_file}" if target_file else "")
        recommended_order.append(f"Implement core logic changes in {target_symbol or 'target'}{loc_str}")

        if direct_dependents:
            top_direct = sorted(direct_dependents)[:4]
            recommended_order.append(f"Update and verify direct dependents: {', '.join(top_direct)}")

        if indirect_dependents:
            top_indirect = sorted(indirect_dependents)[:4]
            recommended_order.append(f"Verify indirect consumers and entry points: {', '.join(top_indirect)}")

        if relevant_tests_list:
            top_tests = relevant_tests_list[:3]
            recommended_order.append(f"Execute and update relevant tests: {', '.join(top_tests)}")
        else:
            recommended_order.append("Add unit tests covering the modified functionality")

        # Extract direct dependencies (callees) of target
        direct_dependencies_list: List[str] = []
        if active_graph and target_symbol:
            try:
                from app.graph.queries import get_dependencies
                dep_res = get_dependencies(active_graph, symbol=target_symbol, max_depth=1)
                if dep_res and hasattr(dep_res, "dependencies"):
                    for d in dep_res.dependencies:
                        direct_dependencies_list.append(d.name)
            except Exception:
                pass

        return CodeChangePlan(
            change_request=change_request,
            target_symbol=target_symbol,
            target_file=target_file,
            target_lines=target_lines,
            direct_dependencies=sorted(list(set(direct_dependencies_list))),
            affected_files=affected_files_list,
            affected_symbols=affected_symbols_list,
            relevant_tests=relevant_tests_list,
            recommended_order=recommended_order,
            risk=risk,
            reason=reason,
            evidence=evidence,
            unverified=unverified,
        )

