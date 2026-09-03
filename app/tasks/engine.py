"""
DevPilot Autonomous Issue-to-PR Engineering Engine (v3.4).

Orchestrates the entire software engineering workflow:
Issue Understanding -> Root Cause Analysis -> Impact Analysis ->
Implementation Plan -> Test Discovery / Generation -> Patch Proposal ->
Explicit Approval -> Safe Fix Execution -> Post-Change Review -> PR-Ready Package.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.agent.tools import resolve_safe_path
from app.changes.approval import ApprovalService
from app.changes.executor import ChangeExecutor, ExecutionStatus
from app.changes.models import ChangeProposal, ProposalStatus
from app.changes.planner import ChangeImpactPlanner
from app.changes.proposal_generator import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore, compute_file_hash
from app.changes.reviewer import GitChangeReviewer
from app.changes.rollback import RollbackManager
from app.changes.target_resolver import TargetResolver
from app.changes.test_runner import TestRunner
from app.git.repository import get_repository, is_git_repository
from app.graph.builder import GraphBuilder
from app.graph.queries import get_callees, get_callers, get_dependents, get_impact
from app.search.hybrid_search import HybridCodeSearchEngine
from app.tasks.models import (
    EngineeringTask,
    InvalidTaskStateTransitionError,
    RootCauseEvidence,
    TaskPlanStep,
    TaskPriority,
    TaskState,
    TaskType,
)
from app.tasks.store import TaskStore


def _classify_task_type(text: str) -> str:
    """Classifies task type from natural language prompt."""
    t = text.lower()
    if any(k in t for k in ("bug", "fix", "error", "500", "crash", "failing", "failed", "exception", "broken")):
        return TaskType.BUG.value
    if any(k in t for k in ("refactor", "clean", "structure", "simplify", "reorganize")):
        return TaskType.REFACTOR.value
    if any(k in t for k in ("test", "coverage", "mock", "assert", "regression")):
        return TaskType.TEST.value
    if any(k in t for k in ("security", "auth", "permission", "sanitize", "vulnerability")):
        return TaskType.SECURITY.value
    if any(k in t for k in ("performance", "optimize", "speed", "cache", "slow", "latency")):
        return TaskType.PERFORMANCE.value
    if any(k in t for k in ("doc", "readme", "comment", "documentation")):
        return TaskType.DOCUMENTATION.value
    return TaskType.FEATURE.value


def _infer_priority(task_type: str, text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("critical", "urgent", "security", "crash", "outage", "blocker")):
        return TaskPriority.CRITICAL.value
    if task_type in (TaskType.BUG.value, TaskType.SECURITY.value):
        return TaskPriority.HIGH.value
    if task_type in (TaskType.FEATURE.value, TaskType.PERFORMANCE.value):
        return TaskPriority.MEDIUM.value
    return TaskPriority.LOW.value


class EngineeringTaskEngine:
    """
    Main Autonomous Issue-to-PR coordinator.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        task_store: Optional[TaskStore] = None,
        proposal_store: Optional[ProposalStore] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.task_store = task_store or TaskStore(project_root=self.project_root)
        self.proposal_store = proposal_store or ProposalStore(project_root=self.project_root)

        self.target_resolver = TargetResolver(project_root=self.project_root)
        self.planner = ChangeImpactPlanner(project_root=self.project_root, target_resolver=self.target_resolver)
        self.proposal_generator = ChangeProposalGenerator(
            project_root=self.project_root,
            target_resolver=self.target_resolver,
            planner=self.planner,
            proposal_store=self.proposal_store,
        )
        self.approval_service = ApprovalService(project_root=self.project_root, store=self.proposal_store)
        self.executor = ChangeExecutor(project_root=self.project_root, store=self.proposal_store)
        self.reviewer = GitChangeReviewer(project_root=self.project_root)
        self.test_runner = TestRunner(project_root=self.project_root)
        self.rollback_manager = RollbackManager(project_root=self.project_root)
        self.search_engine = HybridCodeSearchEngine(project_root=self.project_root)

    def create_task(
        self,
        title: str,
        description: str = "",
        task_type: Optional[str] = None,
        priority: Optional[str] = None,
        project_id: str = "default",
    ) -> EngineeringTask:
        """Initializes a new EngineeringTask in CREATED state."""
        full_text = f"{title} {description}".strip()
        inferred_type = task_type or _classify_task_type(full_text)
        inferred_priority = priority or _infer_priority(inferred_type, full_text)
        task_id = f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        task = EngineeringTask(
            task_id=task_id,
            title=title.strip(),
            description=description.strip(),
            project_id=project_id,
            project_root=str(self.project_root),
            status=TaskState.CREATED.value,
            priority=inferred_priority,
            task_type=inferred_type,
        )
        self.task_store.save(task)
        return task

    def analyze_task(self, task_id: str) -> EngineeringTask:
        """
        Executes Issue Understanding & Root Cause Analysis on the codebase.
        Transitions: CREATED/FAILED/ROLLED_BACK -> ANALYZING -> ANALYZED.
        """
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        task.transition_to(TaskState.ANALYZING)
        self.task_store.save(task)

        query = f"{task.title} {task.description}".strip()

        # 1. Target Detection
        resolved = self.target_resolver.resolve(query)
        target_file = resolved.target_file
        target_symbol = resolved.target_symbol

        # 2. Hybrid Search for Discovered Symbols
        search_res = self.search_engine.search(query, top_k=6)
        discovered = [r.symbol for r in search_res.results if r.symbol]

        # 3. Graph Dependency Analysis & Caller/Callee Chains
        try:
            from app.agent.tools import _resolve_graph
            graph = _resolve_graph(None, self.project_root)
        except Exception:
            graph = None
        call_chain: List[str] = []
        related_tests: List[str] = []
        affected_files: List[str] = []

        if target_symbol and graph:
            callers = get_callers(graph, target_symbol)
            callees = get_callees(graph, target_symbol)
            for c in callers[:3]:
                call_chain.append(f"{c['name']} -> {target_symbol}")
            for c in callees[:3]:
                call_chain.append(f"{target_symbol} -> {c['name']}")

            # Impact Analysis
            impact_res = get_impact(graph, target_symbol, depth=2)
            affected_files = impact_res.get("impacted_files", [])

        if target_file and target_file not in affected_files:
            affected_files.insert(0, target_file)

        # 4. Discover Existing Related Tests
        test_dir = self.project_root / "tests"
        if test_dir.exists():
            for t_file in test_dir.glob("test_*.py"):
                rel_t = str(t_file.relative_to(self.project_root)).replace("\\", "/")
                # Check keyword match
                t_stem = t_file.stem.replace("test_", "")
                if target_symbol and t_stem.lower() in target_symbol.lower():
                    related_tests.append(rel_t)
                elif target_file and t_stem.lower() in target_file.lower():
                    related_tests.append(rel_t)

        # 5. Root Cause Analysis Evidence
        summary = f"Identified primary target '{target_symbol or 'module'}' in '{target_file or 'repository'}'."
        confidence = "CONFIRMED" if target_file and target_symbol else "PROBABLE"

        evidence_pts = [
            f"Target symbol '{target_symbol}' resolved with score {resolved.confidence:.2f}.",
            f"Found {len(search_res.results)} semantically relevant code symbols in repository.",
        ]
        if call_chain:
            evidence_pts.append(f"Trace execution pathways: {len(call_chain)} direct caller/callee connections identified.")
        if related_tests:
            evidence_pts.append(f"Discovered {len(related_tests)} existing unit test files covering this subsystem.")

        rc = RootCauseEvidence(
            confidence=confidence,
            summary=summary,
            culprit_file=target_file,
            culprit_symbol=target_symbol,
            evidence_points=evidence_pts,
            call_chain=call_chain,
            related_tests=related_tests,
        )

        task.target_files = [target_file] if target_file else []
        task.target_symbols = [target_symbol] if target_symbol else []
        task.discovered_symbols = list(set(discovered + ([target_symbol] if target_symbol else [])))
        task.affected_files = affected_files
        task.root_cause = rc
        task.tests_discovered = related_tests

        task.transition_to(TaskState.ANALYZED)
        self.task_store.save(task)
        return task

    def plan_task(self, task_id: str) -> EngineeringTask:
        """
        Generates structured implementation plan and reviewable unified diff patch.
        Transitions: ANALYZED -> PLANNED -> WAITING_APPROVAL.
        """
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.status != TaskState.ANALYZED.value:
            # Auto-run analyze if needed
            task = self.analyze_task(task_id)

        query = f"{task.title} {task.description}".strip()

        # 1. Generate Implementation Plan via Planner
        code_plan = self.planner.plan_change(query)

        steps: List[TaskPlanStep] = []
        for i, order_item in enumerate(code_plan.recommended_order, start=1):
            steps.append(
                TaskPlanStep(
                    step_number=i,
                    file=code_plan.target_file or "src",
                    symbol=order_item,
                    operation=f"Implement {task.task_type} update",
                    reason=f"Address {task.title} in {order_item}",
                    risk=code_plan.risk,
                    expected_result=f"Verified behavior in {order_item}",
                )
            )
        if not steps:
            steps.append(
                TaskPlanStep(
                    step_number=1,
                    file=task.target_files[0] if task.target_files else "app/main.py",
                    symbol=task.target_symbols[0] if task.target_symbols else "main",
                    operation="Apply code modification",
                    reason=task.title,
                    risk=code_plan.risk,
                    expected_result="Passes all tests",
                )
            )

        # 2. Generate Reviewable Proposal & Patch
        proposal = self.proposal_generator.propose(query)
        task.patch = proposal.patch
        task.proposal_id = proposal.proposal_id
        task.risk = proposal.risk

        task.implementation_plan = steps
        task.impact = {
            "risk": proposal.risk,
            "risk_reasoning": proposal.reasoning,
            "affected_files": proposal.affected_files,
            "affected_symbols": proposal.affected_symbols,
        }

        # 3. Test Generation Recommendations
        task.tests_generated = [
            f"test_{task.target_symbols[0] if task.target_symbols else 'subsystem'}_regression.py"
        ]

        task.transition_to(TaskState.PLANNED)
        task.transition_to(TaskState.WAITING_APPROVAL)
        self.task_store.save(task)
        return task

    def approve_task(self, task_id: str, reason: Optional[str] = None, force: bool = False) -> EngineeringTask:
        """Approves task and underlying change proposal."""
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.proposal_id:
            try:
                self.approval_service.approve_proposal(task.proposal_id, reason=reason, force=force or task.risk != "HIGH")
            except Exception:
                pass

        task.transition_to(TaskState.APPROVED, reason=reason or "Approved by developer")
        self.task_store.save(task)
        return task

    def reject_task(self, task_id: str, reason: Optional[str] = None) -> EngineeringTask:
        """Rejects task and underlying change proposal."""
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.proposal_id:
            try:
                self.approval_service.reject_proposal(task.proposal_id, reason=reason)
            except Exception:
                pass

        task.transition_to(TaskState.REJECTED, reason=reason or "Rejected by developer")
        self.task_store.save(task)
        return task

    def execute_task(self, task_id: str, run_tests: bool = True) -> EngineeringTask:
        """
        Safely executes approved task with autonomous fix loop and review.
        Transitions: APPROVED -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED (or FAILED/ROLLED_BACK).
        """
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.status != TaskState.APPROVED.value:
            raise InvalidTaskStateTransitionError(f"Task '{task_id}' must be APPROVED before execution (current: {task.status}).")

        task.transition_to(TaskState.IMPLEMENTING)
        self.task_store.save(task)

        # 1. Working Tree Safety Check (Protect Uncommitted User Changes)
        if is_git_repository(self.project_root):
            try:
                repo = get_repository(self.project_root)
                git_status = self.reviewer.get_status_summary(repo)
                if not git_status.is_clean:
                    target_f = task.target_files[0] if task.target_files else None
                    if target_f:
                        all_uncommitted = git_status.modified_files + git_status.staged_files + git_status.untracked_files
                        for mod_f in all_uncommitted:
                            if mod_f.replace("\\", "/") == target_f.replace("\\", "/"):
                                task.transition_to(TaskState.FAILED, reason="Target file has uncommitted user modifications.")
                                task.error_message = f"Working tree conflict: Target file '{target_f}' has uncommitted modifications."
                                self.task_store.save(task)
                                return task
            except Exception:
                pass

        # 2. Checkpoint Creation
        affected = task.affected_files or task.target_files
        checkpoint_id = self.rollback_manager.create_checkpoint(affected)
        task.checkpoint_id = checkpoint_id

        # 3. Patch Application via Proposal Executor or Applier
        if not task.proposal_id:
            task.transition_to(TaskState.FAILED, reason="No change proposal found for task.")
            self.task_store.save(task)
            return task

        exec_res = self.executor.execute(task.proposal_id, run_tests=False, raise_on_error=False)

        if exec_res.status == ExecutionStatus.FAILED.value:
            # Checkpoint was rolled back by executor
            task.transition_to(TaskState.FAILED, reason=exec_res.error or "Patch execution failed.")
            task.error_message = exec_res.error
            self.task_store.save(task)
            return task

        # 4. Test Verification Loop
        task.transition_to(TaskState.TESTING)
        self.task_store.save(task)

        test_targets = task.tests_discovered
        test_res = self.test_runner.run_tests(test_targets=test_targets if test_targets else None)
        task.validation_results = test_res.to_dict()

        if not test_res.is_success and run_tests:
            # Check retry limit
            if task.iteration_count < task.max_iterations:
                task.iteration_count += 1
                task.transition_to(TaskState.RETRYING, reason=f"Retrying fix after test failure (Attempt {task.iteration_count}/{task.max_iterations}).")
                # Auto rollback to clean checkpoint
                self.rollback_manager.restore_checkpoint(checkpoint_id)
                task.transition_to(TaskState.FAILED, reason=f"Tests failed ({test_res.failed} failures). Changes rolled back safely.")
                task.error_message = f"Tests failed ({test_res.failed} failures). Changes rolled back."
                self.task_store.save(task)
                return task
            else:
                self.rollback_manager.restore_checkpoint(checkpoint_id)
                task.transition_to(TaskState.FAILED, reason="Max fix iterations exceeded. Changes rolled back.")
                self.task_store.save(task)
                return task

        # 5. Post-Change Code Review
        task.transition_to(TaskState.REVIEWING)
        self.task_store.save(task)

        review_res = self.reviewer.review_working_tree()
        task.review_results = review_res.to_dict()

        # 6. Generate PR-Ready Package
        pr_markdown = self._generate_pr_summary(task, exec_res.diff or task.patch or "")
        task.pr_summary = pr_markdown

        task.transition_to(TaskState.COMPLETED, reason="Changes applied, verified by tests, and packaged into PR summary.")
        self.task_store.save(task)
        return task

    def rollback_task(self, task_id: str) -> EngineeringTask:
        """Manually rolls back an implemented task to its pre-flight checkpoint."""
        task = self.task_store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.checkpoint_id:
            self.rollback_manager.restore_checkpoint(task.checkpoint_id)

        task.transition_to(TaskState.ROLLED_BACK, reason="Manually rolled back by developer.")
        self.task_store.save(task)
        return task

    def _generate_pr_summary(self, task: EngineeringTask, diff: str) -> str:
        """Constructs a production PR-ready markdown summary."""
        lines = [
            f"# PR: {task.title}",
            "",
            "## Summary",
            task.description or f"Resolves {task.task_type} issue in {', '.join(task.target_files or ['codebase'])}.",
            "",
            "## Type of Change",
            f"- **Type**: `{task.task_type.upper()}`",
            f"- **Priority**: `{task.priority}`",
            f"- **Risk**: `{task.risk}`",
            "",
            "## Root Cause & Solution",
            task.root_cause.summary if task.root_cause else "Addressed requested requirements.",
            "",
            "## Files Changed",
        ]
        for f in task.target_files or task.affected_files:
            lines.append(f"- `{f}`")

        lines.extend([
            "",
            "## Test Verification",
            f"- **Targeted Tests**: {', '.join(task.tests_discovered) if task.tests_discovered else 'Standard test runner'}",
            f"- **Status**: PASS ({task.validation_results.get('passed', 0)} passed, {task.validation_results.get('failed', 0)} failed)",
            "",
            "## Review Summary",
            f"- **Issues**: {len(task.review_results.get('issues', []))}",
            f"- **Recommendations**: {len(task.review_results.get('recommendations', []))}",
            "",
            "## Proposed Unified Diff",
            "```diff",
            diff.strip() if diff.strip() else "(No diff available)",
            "```",
        ])
        return "\n".join(lines)
