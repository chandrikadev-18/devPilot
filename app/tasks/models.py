"""
DevPilot Autonomous Issue-to-PR Task Engineering Models (v3.4).

Defines structured task models, lifecycle states, state transitions,
root cause analysis evidence, and PR-ready change packages.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class TaskType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"
    TEST = "test"
    DOCUMENTATION = "documentation"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskState(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    PLANNED = "PLANNED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    ROLLED_BACK = "ROLLED_BACK"
    REJECTED = "REJECTED"


# Valid state machine transitions
ALLOWED_STATE_TRANSITIONS: Dict[TaskState, List[TaskState]] = {
    TaskState.CREATED: [TaskState.ANALYZING, TaskState.REJECTED],
    TaskState.ANALYZING: [TaskState.ANALYZED, TaskState.FAILED],
    TaskState.ANALYZED: [TaskState.PLANNED, TaskState.REJECTED],
    TaskState.PLANNED: [TaskState.WAITING_APPROVAL, TaskState.REJECTED],
    TaskState.WAITING_APPROVAL: [TaskState.APPROVED, TaskState.REJECTED],
    TaskState.APPROVED: [TaskState.IMPLEMENTING, TaskState.REJECTED],
    TaskState.IMPLEMENTING: [TaskState.TESTING, TaskState.FAILED, TaskState.ROLLED_BACK],
    TaskState.TESTING: [TaskState.REVIEWING, TaskState.RETRYING, TaskState.FAILED, TaskState.ROLLED_BACK],
    TaskState.RETRYING: [TaskState.IMPLEMENTING, TaskState.FAILED, TaskState.ROLLED_BACK],
    TaskState.REVIEWING: [TaskState.COMPLETED, TaskState.FAILED],
    TaskState.FAILED: [TaskState.RETRYING, TaskState.ROLLED_BACK, TaskState.ANALYZING],
    TaskState.ROLLED_BACK: [TaskState.ANALYZING, TaskState.REJECTED],
    TaskState.COMPLETED: [],
    TaskState.REJECTED: [],
}


class InvalidTaskStateTransitionError(Exception):
    """Raised when an illegal task state transition is attempted."""
    pass


def validate_task_transition(current: TaskState, target: TaskState) -> None:
    """Enforces strict deterministic state machine rules."""
    allowed = ALLOWED_STATE_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise InvalidTaskStateTransitionError(
            f"Cannot transition task from '{current.value}' to '{target.value}'. "
            f"Allowed transitions: {[s.value for s in allowed]}"
        )


@dataclass
class RootCauseEvidence:
    """Structured root-cause findings for bug and regression issues."""
    confidence: str = "PROBABLE"  # CONFIRMED, PROBABLE, UNKNOWN
    summary: str = ""
    culprit_file: Optional[str] = None
    culprit_symbol: Optional[str] = None
    evidence_points: List[str] = field(default_factory=list)
    call_chain: List[str] = field(default_factory=list)
    related_tests: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence": self.confidence,
            "summary": self.summary,
            "culprit_file": self.culprit_file,
            "culprit_symbol": self.culprit_symbol,
            "evidence_points": self.evidence_points,
            "call_chain": self.call_chain,
            "related_tests": self.related_tests,
        }


@dataclass
class TaskPlanStep:
    """Individual action step in an implementation plan."""
    step_number: int
    file: str
    symbol: str
    operation: str
    reason: str
    risk: str = "LOW"
    expected_result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "file": self.file,
            "symbol": self.symbol,
            "operation": self.operation,
            "reason": self.reason,
            "risk": self.risk,
            "expected_result": self.expected_result,
        }


@dataclass
class EngineeringTask:
    """
    Unified representation of an autonomous issue-to-PR engineering task.
    """
    task_id: str
    title: str
    description: str
    project_id: str = "default"
    project_root: str = "."
    status: str = TaskState.CREATED.value
    priority: str = TaskPriority.MEDIUM.value
    task_type: str = TaskType.BUG.value

    # Target & Discovered Entities
    target_files: List[str] = field(default_factory=list)
    target_symbols: List[str] = field(default_factory=list)
    discovered_symbols: List[str] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)

    # Intelligence & Analysis
    root_cause: Optional[RootCauseEvidence] = None
    impact: Dict[str, Any] = field(default_factory=dict)
    implementation_plan: List[TaskPlanStep] = field(default_factory=list)
    patch: Optional[str] = None
    proposal_id: Optional[str] = None

    # Verification & Review
    tests_discovered: List[str] = field(default_factory=list)
    tests_generated: List[str] = field(default_factory=list)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    review_results: Dict[str, Any] = field(default_factory=dict)
    pr_summary: Optional[str] = None

    # Execution Tracking
    risk: str = "LOW"
    iteration_count: int = 0
    max_iterations: int = 3
    checkpoint_id: Optional[str] = None
    error_message: Optional[str] = None
    decision_reason: Optional[str] = None

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def transition_to(self, new_state: TaskState, reason: Optional[str] = None) -> None:
        curr_enum = TaskState(self.status)
        validate_task_transition(curr_enum, new_state)
        self.status = new_state.value
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if reason:
            self.decision_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "project_id": self.project_id,
            "project_root": self.project_root,
            "status": self.status,
            "priority": self.priority,
            "task_type": self.task_type,
            "target_files": self.target_files,
            "target_symbols": self.target_symbols,
            "discovered_symbols": self.discovered_symbols,
            "affected_files": self.affected_files,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "impact": self.impact,
            "implementation_plan": [s.to_dict() for s in self.implementation_plan],
            "patch": self.patch,
            "proposal_id": self.proposal_id,
            "tests_discovered": self.tests_discovered,
            "tests_generated": self.tests_generated,
            "validation_results": self.validation_results,
            "review_results": self.review_results,
            "pr_summary": self.pr_summary,
            "risk": self.risk,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "checkpoint_id": self.checkpoint_id,
            "error_message": self.error_message,
            "decision_reason": self.decision_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EngineeringTask":
        rc_data = d.get("root_cause")
        rc = RootCauseEvidence(**rc_data) if rc_data and isinstance(rc_data, dict) else None

        plan_data = d.get("implementation_plan", [])
        plan = [TaskPlanStep(**p) if isinstance(p, dict) else p for p in plan_data]

        return cls(
            task_id=d.get("task_id", f"task_{uuid.uuid4().hex[:8]}"),
            title=d.get("title", ""),
            description=d.get("description", ""),
            project_id=d.get("project_id", "default"),
            project_root=d.get("project_root", "."),
            status=d.get("status", TaskState.CREATED.value),
            priority=d.get("priority", TaskPriority.MEDIUM.value),
            task_type=d.get("task_type", TaskType.BUG.value),
            target_files=d.get("target_files", []),
            target_symbols=d.get("target_symbols", []),
            discovered_symbols=d.get("discovered_symbols", []),
            affected_files=d.get("affected_files", []),
            root_cause=rc,
            impact=d.get("impact", {}),
            implementation_plan=plan,
            patch=d.get("patch"),
            proposal_id=d.get("proposal_id"),
            tests_discovered=d.get("tests_discovered", []),
            tests_generated=d.get("tests_generated", []),
            validation_results=d.get("validation_results", {}),
            review_results=d.get("review_results", {}),
            pr_summary=d.get("pr_summary"),
            risk=d.get("risk", "LOW"),
            iteration_count=d.get("iteration_count", 0),
            max_iterations=d.get("max_iterations", 3),
            checkpoint_id=d.get("checkpoint_id"),
            error_message=d.get("error_message"),
            decision_reason=d.get("decision_reason"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=d.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
