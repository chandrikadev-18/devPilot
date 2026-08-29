"""
DevPilot Intelligent Change Proposal Generator (v2.1).

Converts natural-language change requests into structured, reviewable code-change
proposals with unified diff patches, impact analysis, risk reasoning, test recommendations,
and pre-application review summaries WITHOUT modifying files on disk.
"""

import difflib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.tools import resolve_safe_path
from app.changes.diff_generator import DiffGenerator
from app.changes.models import ChangeProposal, CodeChangePlan, FileChangeItem, ProposalStatus
from app.changes.patch import CodeChangePatchGenerator
from app.changes.planner import ChangeImpactPlanner
from app.changes.proposal_store import ProposalStore, compute_file_hash, generate_proposal_id
from app.changes.target_resolver import ResolvedTarget, TargetResolver
from app.graph.store import GraphStore
from app.llm import LLMProvider, create_llm_provider
from app.parser.python_parser import PythonParser


def _derive_proposed_changes(request: str, target_symbol: str) -> List[str]:
    """Derives itemized, human-readable proposed changes from change request."""
    req_lower = request.lower()
    changes: List[str] = []

    # Logging patterns
    if "logging" in req_lower or "log " in req_lower or "logger" in req_lower:
        if "start" in req_lower or "begin" in req_lower:
            changes.append("Add start logging")
        if "finish" in req_lower or "end" in req_lower or "complete" in req_lower:
            changes.append("Add completion logging")
        if "error" in req_lower or "exception" in req_lower:
            changes.append("Add error logging")
        if not changes:
            changes.append(f"Add structured logging to {target_symbol}")
        changes.append("Preserve existing return behavior")
        return changes

    # Validation / Error handling
    if "validate" in req_lower or "validation" in req_lower or "check" in req_lower:
        changes.append("Add input validation and boundary checks")
        changes.append("Raise appropriate error on invalid parameters")
        changes.append("Preserve existing return signature")
        return changes

    # Performance / Cache / Optimization
    if "optimize" in req_lower or "performance" in req_lower or "cache" in req_lower:
        changes.append("Optimize core execution path")
        changes.append("Introduce efficient caching / lookup")
        changes.append("Preserve external behavior and return types")
        return changes

    # Refactor / Cleanup
    if "refactor" in req_lower or "clean" in req_lower:
        changes.append(f"Refactor internal implementation of {target_symbol}")
        changes.append("Extract helper functions if complexity is high")
        changes.append("Preserve existing public API and return values")
        return changes

    # General fallback
    changes.append(f"Implement requested modifications in {target_symbol}")
    changes.append("Verify inputs and boundary conditions")
    changes.append("Preserve existing behavior and return signature")
    return changes


class ChangeProposalGenerator:
    """
    Constructs structured, reviewable code-change proposals from natural language requests.
    Strictly read-only; never writes to files or applies patches.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        llm: Optional[LLMProvider] = None,
        target_resolver: Optional[TargetResolver] = None,
        planner: Optional[ChangeImpactPlanner] = None,
        proposal_store: Optional[ProposalStore] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.llm = llm
        self.target_resolver = target_resolver or TargetResolver(project_root=self.project_root)
        self.planner = planner or ChangeImpactPlanner(project_root=self.project_root, target_resolver=self.target_resolver)
        self.patch_generator = CodeChangePatchGenerator(project_root=self.project_root, llm=self.llm, planner=self.planner)
        self.diff_generator = DiffGenerator(project_root=self.project_root)
        self.proposal_store = proposal_store or ProposalStore(project_root=self.project_root)

    def propose(
        self,
        change_request: str,
        graph: Optional[GraphStore] = None,
    ) -> ChangeProposal:
        """
        Plans change impact, synthesizes unified diff patch, and generates
        a structured ChangeProposal without modifying files.
        """
        if not change_request or not change_request.strip():
            return ChangeProposal(
                request=change_request or "",
                target_symbol=None,
                target_file=None,
                target_lines=None,
                change_summary="Change request cannot be empty.",
                affected_files=[],
                affected_symbols=[],
                proposed_changes=[],
                patch="",
                tests_to_update=[],
                tests_to_add=[],
                risk="LOW",
                reasoning="Change request cannot be empty.",
                confidence=0.0,
                warnings=["Change request cannot be empty."],
                unverified_assumptions=[],
                status="PROPOSAL_ONLY",
            )

        q_clean = change_request.strip()

        # Step 1: Resolve Dependency Graph
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        # Step 2: Target Resolution
        resolved_target: ResolvedTarget = self.target_resolver.resolve(
            request=q_clean,
            graph=active_graph,
        )

        warnings: List[str] = list(resolved_target.unverified)
        unverified_assumptions: List[str] = []

        # Handle Ambiguity
        if resolved_target.is_ambiguous:
            return ChangeProposal(
                request=q_clean,
                target_symbol=resolved_target.target_symbol or resolved_target.target,
                target_file=None,
                target_lines=None,
                change_summary=f"Target symbol '{resolved_target.target_symbol}' is ambiguous.",
                affected_files=[],
                affected_symbols=[],
                proposed_changes=[
                    f"Disambiguate target symbol '{resolved_target.target_symbol}' by providing qualified name (Class.method) or file path."
                ],
                patch="",
                tests_to_update=[],
                tests_to_add=[],
                risk="HIGH",
                reasoning="Ambiguous symbol matches multiple definitions across different files.",
                confidence=0.0,
                warnings=warnings or ["Target symbol is ambiguous."],
                unverified_assumptions=["Assumes symbol uniquely identifies code location."],
                status="PROPOSAL_ONLY",
            )

        # Handle Unresolved / Non-existent Target
        if not resolved_target.target_file or resolved_target.confidence == 0.0:
            warning_msg = (
                f"Target '{resolved_target.target_symbol or q_clean}' cannot be confidently identified "
                f"in the codebase. Please specify an exact symbol or file."
            )
            warnings.append(warning_msg)
            return ChangeProposal(
                request=q_clean,
                target_symbol=resolved_target.target_symbol,
                target_file=None,
                target_lines=None,
                change_summary=warning_msg,
                affected_files=[],
                affected_symbols=[],
                proposed_changes=[],
                patch="",
                tests_to_update=[],
                tests_to_add=[],
                risk="LOW",
                reasoning="Target symbol could not be verified in codebase.",
                confidence=0.0,
                warnings=warnings,
                unverified_assumptions=[f"Target '{resolved_target.target_symbol or q_clean}' was not found in static graph or AST."],
                status="PROPOSAL_ONLY",
            )

        # Step 3: Change Impact Planning
        plan: CodeChangePlan = self.planner.plan_change(change_request=q_clean, graph=active_graph)

        target_sym = plan.target_symbol or resolved_target.target_symbol or "target"
        target_f = plan.target_file or resolved_target.target_file or ""
        target_lines_str = plan.target_lines or resolved_target.target_lines

        # Step 4: Proposed Changes Itemization
        proposed_changes = _derive_proposed_changes(q_clean, target_sym)

        # Step 5: Test Intelligence
        tests_to_update: List[str] = []
        tests_to_add: List[str] = []

        for t in plan.relevant_tests:
            if t.endswith(".py") or ":" in t:
                # Extract base test file
                t_f = t.split(" ")[-1].strip("()") if " " in t else t
                t_clean = t_f.split(":")[0]
                if t_clean not in tests_to_update:
                    tests_to_update.append(t_clean)

        # Direct test mapping for target file
        if target_f:
            stem = Path(target_f).stem
            cand_test = f"tests/test_{stem}.py"
            if (self.project_root / cand_test).exists() and cand_test not in tests_to_update:
                tests_to_update.append(cand_test)

        # Suggest regression test addition
        req_verb = "logging behavior" if "log" in q_clean.lower() else "modified behavior"
        tests_to_add.append(f"Add regression test for {req_verb} if appropriate")

        # Step 6: Patch Synthesis via Intelligent Diff Generator (Read-only)
        patch_str = ""
        if target_f:
            try:
                gen_patch, gen_warnings = self.diff_generator.generate_diff(
                    request=q_clean,
                    target_file=target_f,
                    target_symbol=target_sym,
                    target_lines=target_lines_str,
                )
                patch_str = gen_patch
                if gen_warnings:
                    warnings.extend(gen_warnings)
            except Exception as e:
                warnings.append(f"Diff generator warning: {e}")

        # Fallback to legacy patch generator if patch_str is still empty
        if not patch_str:
            try:
                legacy_proposal = self.patch_generator.generate_patch(change_request=q_clean, graph=active_graph)
                patch_str = legacy_proposal.patch or ""
            except Exception:
                patch_str = ""

        affected_files_list = sorted(list(set(plan.affected_files + ([target_f] if target_f else []))))
        affected_symbols_list = sorted(list(set(plan.affected_symbols + ([target_sym] if target_sym else []))))

        change_summary_str = (
            f"Proposed modification to {target_sym} in {target_f} "
            f"with blast radius across {len(plan.affected_symbols)} dependent symbol(s)."
        )

        target_hash = None
        if target_f:
            try:
                full_p = resolve_safe_path(target_f, self.project_root)
                target_hash = compute_file_hash(full_p)
            except Exception:
                pass

        proposal = ChangeProposal(
            request=q_clean,
            proposal_id=generate_proposal_id(),
            target_symbol=target_sym,
            target_file=target_f,
            target_lines=target_lines_str,
            change_summary=change_summary_str,
            affected_files=affected_files_list,
            affected_symbols=affected_symbols_list,
            proposed_changes=proposed_changes,
            patch=patch_str,
            tests_to_update=sorted(tests_to_update),
            tests_to_add=tests_to_add,
            risk=plan.risk,
            reasoning=plan.reason,
            confidence=resolved_target.confidence,
            warnings=warnings,
            unverified_assumptions=unverified_assumptions,
            status=ProposalStatus.PENDING_APPROVAL.value,
            target_content_hash=target_hash,
        )

        return self.proposal_store.save(proposal)
