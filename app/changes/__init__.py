"""
DevPilot Code Change Intelligence Module.
"""

from app.changes.analyzer import CodeChangeAnalyzer
from app.changes.autonomous_fix import AutonomousFixService, FixOrchestrator
from app.changes.detector import detect_changed_symbols
from app.changes.git_intelligence import GitChangeIntelligenceService
from app.changes.approval import (
    AlreadyAppliedError,
    ApprovalError,
    ApprovalService,
    DuplicateApprovalError,
    HighRiskConfirmationError,
    ProposalNotFoundError,
    RejectedProposalError,
    StaleProposalError,
)
from app.changes.executor import (
    ChangeExecutor,
    ExecutionError,
    InvalidPatchError,
    PatchExecutionError,
    StalePatchError,
    SyntaxValidationError,
    TestExecutionFailureError,
    UnapprovedProposalError,
)
from app.changes.failure_analyzer import FailureAnalyzer
from app.changes.fix_loop import FixLoopService
from app.changes.models import (
    AutonomousFixResult,
    ChangeExecution,
    ChangeImpact,
    ChangePlanEvidence,
    ChangeProposal,
    ChangeRisk,
    ChangedSymbol,
    CodeChangeAnalysis,
    CodeChangePlan,
    CodeChangeProposal,
    ExecutionStatus,
    FailureAnalysis,
    FileChangeItem,
    FixIteration,
    FixIterationStatus,
    FixLoopResult,
    FixMode,
    GitChangeReview,
    GitStatusSummary,
    PatchApplicationResult,
    PatchValidationResult,
    ProposalStatus,
    RiskLevel,
    RollbackResult,
    SymbolChangeType,
    TestRecommendation,
    TestValidationResult,
)
from app.changes.patch import CodeChangePatchGenerator
from app.changes.patch_applier import PatchApplier
from app.changes.patch_validator import PatchValidator
from app.changes.planner import ChangeImpactPlanner
from app.changes.proposal_generator import ChangeProposalGenerator
from app.changes.proposal_store import ProposalStore
from app.changes.reviewer import GitChangeReviewer
from app.changes.risk import calculate_change_risk, calculate_plan_risk
from app.changes.rollback import RollbackManager
from app.changes.service import SafePatchService
from app.changes.target_resolver import ResolvedTarget, TargetResolver
from app.changes.test_runner import TestRunner


__all__ = [
    "CodeChangeAnalyzer",
    "ChangeImpactPlanner",
    "ChangeProposalGenerator",
    "ChangeProposal",
    "ProposalStatus",
    "ProposalStore",
    "ApprovalService",
    "ApprovalError",
    "ProposalNotFoundError",
    "DuplicateApprovalError",
    "RejectedProposalError",
    "AlreadyAppliedError",
    "StaleProposalError",
    "HighRiskConfirmationError",
    "ChangeExecutor",
    "ChangeExecution",
    "ExecutionStatus",
    "ExecutionError",
    "UnapprovedProposalError",
    "InvalidPatchError",
    "StalePatchError",
    "PatchExecutionError",
    "SyntaxValidationError",
    "TestExecutionFailureError",
    "FailureAnalyzer",
    "FailureAnalysis",
    "FixLoopService",
    "FixLoopResult",
    "FixIteration",
    "FixIterationStatus",
    "DiffGenerator",

    "GitChangeIntelligenceService",
    "TargetResolver",
    "ResolvedTarget",
    "CodeChangePatchGenerator",
    "GitChangeReviewer",
    "SafePatchService",
    "PatchValidator",
    "PatchApplier",
    "RollbackManager",
    "TestRunner",
    "AutonomousFixService",
    "FixOrchestrator",
    "FixMode",
    "AutonomousFixResult",
    "detect_changed_symbols",
    "calculate_change_risk",
    "calculate_plan_risk",
    "CodeChangeAnalysis",
    "CodeChangePlan",
    "CodeChangeProposal",
    "FileChangeItem",
    "GitChangeReview",
    "GitStatusSummary",
    "TestRecommendation",
    "PatchValidationResult",
    "PatchApplicationResult",
    "TestValidationResult",
    "RollbackResult",
    "ChangePlanEvidence",
    "ChangedSymbol",
    "ChangeImpact",
    "ChangeRisk",
    "SymbolChangeType",
    "RiskLevel",
]

