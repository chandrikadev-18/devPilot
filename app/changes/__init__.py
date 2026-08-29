"""
DevPilot Code Change Intelligence Module.
"""

from app.changes.analyzer import CodeChangeAnalyzer
from app.changes.detector import detect_changed_symbols
from app.changes.models import (
    ChangeImpact,
    ChangePlanEvidence,
    ChangeRisk,
    ChangedSymbol,
    CodeChangeAnalysis,
    CodeChangePlan,
    CodeChangeProposal,
    FileChangeItem,
    GitChangeReview,
    GitStatusSummary,
    PatchApplicationResult,
    PatchValidationResult,
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
from app.changes.reviewer import GitChangeReviewer
from app.changes.risk import calculate_change_risk, calculate_plan_risk
from app.changes.rollback import RollbackManager
from app.changes.service import SafePatchService
from app.changes.test_runner import TestRunner

__all__ = [
    "CodeChangeAnalyzer",
    "ChangeImpactPlanner",
    "CodeChangePatchGenerator",
    "GitChangeReviewer",
    "SafePatchService",
    "PatchValidator",
    "PatchApplier",
    "RollbackManager",
    "TestRunner",
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
