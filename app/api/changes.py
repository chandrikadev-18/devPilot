"""
DevPilot Code Change Intelligence API Router.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.changes.analyzer import CodeChangeAnalyzer
from app.git.repository import GitCommitNotFoundError, GitError, NotAGitRepositoryError
from app.schemas.changes import (
    AnalyzeChangeRequest,
    AnalyzeChangeResponse,
    AutonomousFixRequest,
    AutonomousFixResponse,
    ChangedSymbolItem,
    ChangeImpactItem,
    ChangePlanEvidenceItem,
    ChangeRiskItem,
    GitStatusSummaryItem,
    GitChangeItem,
    GitChangeSummaryResponse,
    ChangeProposalRequest,
    ChangeProposalResponse,
    ApproveProposalRequest,
    RejectProposalRequest,
    ExecuteProposalRequest,
    ChangeExecutionResponse,
    FixLoopRequest,
    FixLoopResponse,
    PlanChangeRequest,
    PlanChangeResponse,

    ReviewChangeRequest,
    ReviewChangeResponse,
    TestRecommendationItem,
)



router = APIRouter(prefix="/changes", tags=["Code Change Intelligence"])


def _run_change_analysis(commit: str, project_dir: str) -> AnalyzeChangeResponse:
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project directory does not exist: '{project_dir}'",
        )

    try:
        analyzer = CodeChangeAnalyzer(project_root=root)
        analysis = analyzer.analyze_commit(commit_hash=commit or "HEAD")
        return AnalyzeChangeResponse(
            commit=analysis.commit,
            short_hash=analysis.short_hash,
            author=analysis.author,
            date=analysis.date,
            message=analysis.message,
            changed_files=analysis.changed_files,
            changed_symbols=[
                ChangedSymbolItem(
                    name=s.name,
                    file=s.file,
                    change_type=s.change_type,
                    symbol_type=s.symbol_type,
                    line_start=s.line_start,
                    line_end=s.line_end,
                )
                for s in analysis.changed_symbols
            ],
            impact=ChangeImpactItem(
                direct=analysis.impact.direct_dependents,
                indirect=analysis.impact.indirect_dependents,
                files=analysis.impact.impacted_files,
                total_affected_symbols=analysis.impact.total_affected_symbols,
            ),
            risk=ChangeRiskItem(
                score=analysis.risk.score,
                level=analysis.risk.level,
                reasons=analysis.risk.reasons,
            ),
        )
    except GitCommitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotAGitRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (GitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing code changes: {str(e)}")


@router.post(
    "/analyze",
    response_model=AnalyzeChangeResponse,
    summary="Analyze Code Changes in a Commit (POST)",
    description="Detects changed AST symbols in a commit, calculates static dependency graph impact, and scores change risk.",
)
def analyze_code_change_post(
    request: AnalyzeChangeRequest,
) -> AnalyzeChangeResponse:
    return _run_change_analysis(commit=request.commit, project_dir=request.project_dir)


@router.get(
    "/analyze",
    response_model=AnalyzeChangeResponse,
    summary="Analyze Code Changes in a Commit (GET)",
    description="Detects changed AST symbols in a commit, calculates static dependency graph impact, and scores change risk.",
)
def analyze_code_change_get(
    commit: str = Query("HEAD", description="Git commit hash, short SHA, or revision"),
    project_dir: str = Query(".", description="Target project directory"),
) -> AnalyzeChangeResponse:
    return _run_change_analysis(commit=commit, project_dir=project_dir)


def _run_change_plan(change_request: str, project_dir: str) -> PlanChangeResponse:
    if not change_request or not change_request.strip():
        raise HTTPException(status_code=400, detail="Change request cannot be empty.")

    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    try:
        from app.changes.planner import ChangeImpactPlanner
        from app.schemas.changes import ChangePlanEvidenceItem, PlanChangeResponse
        planner = ChangeImpactPlanner(project_root=root)
        plan = planner.plan_change(change_request=change_request)

        return PlanChangeResponse(
            change_request=plan.change_request,
            target=plan.target_symbol or plan.target_file or "Unknown",
            target_symbol=plan.target_symbol,
            target_file=plan.target_file,
            target_lines=plan.target_lines,
            affected_files=plan.affected_files,
            affected_symbols=plan.affected_symbols,
            relevant_tests=plan.relevant_tests,
            recommended_order=plan.recommended_order,
            risk=plan.risk,
            reason=plan.reason,
            evidence=[
                ChangePlanEvidenceItem(
                    file=e.file,
                    symbol=e.symbol,
                    lines=e.lines,
                    relationship=e.relationship,
                )
                for e in plan.evidence
            ],
            unverified=plan.unverified,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error planning code change: {str(e)}")


@router.post(
    "/plan",
    response_model=PlanChangeResponse,
    summary="Plan Code Change Implementation (POST)",
    description="Constructs a grounded implementation plan with affected files, dependent symbols, tests, implementation order, and risk.",
)
def plan_code_change_post(
    request: PlanChangeRequest,
) -> PlanChangeResponse:
    return _run_change_plan(change_request=request.change_request, project_dir=request.project_dir)


@router.get(
    "/plan",
    response_model=PlanChangeResponse,
    summary="Plan Code Change Implementation (GET)",
    description="Constructs a grounded implementation plan with affected files, dependent symbols, tests, implementation order, and risk.",
)
def plan_code_change_get(
    change_request: str = Query(..., min_length=1, description="Developer change request or refactoring goal"),
    project_dir: str = Query(".", description="Target project directory"),
) -> PlanChangeResponse:
    return _run_change_plan(change_request=change_request, project_dir=project_dir)


def _run_change_review(project_dir: str) -> ReviewChangeResponse:
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project directory does not exist: '{project_dir}'",
        )

    try:
        from app.changes.reviewer import GitChangeReviewer
        reviewer = GitChangeReviewer(project_root=root)
        review = reviewer.review_working_tree()

        return ReviewChangeResponse(
            branch=review.branch,
            base_branch=review.base_branch,
            is_clean=review.is_clean,
            status=GitStatusSummaryItem(
                branch=review.status.branch,
                base_branch=review.status.base_branch,
                is_clean=review.status.is_clean,
                modified_files=review.status.modified_files,
                added_files=review.status.added_files,
                deleted_files=review.status.deleted_files,
                renamed_files=review.status.renamed_files,
                untracked_files=review.status.untracked_files,
                staged_files=review.status.staged_files,
                unstaged_files=review.status.unstaged_files,
                ahead_commits=review.status.ahead_commits,
                behind_commits=review.status.behind_commits,
            ),
            changed_files=review.changed_files,
            changed_symbols=[
                ChangedSymbolItem(
                    name=s.name,
                    file=s.file,
                    change_type=s.change_type,
                    symbol_type=s.symbol_type,
                    line_start=s.line_start,
                    line_end=s.line_end,
                )
                for s in review.changed_symbols
            ],
            impact=ChangeImpactItem(
                direct=review.impact.direct_dependents,
                indirect=review.impact.indirect_dependents,
                files=review.impact.impacted_files,
                total_affected_symbols=review.impact.total_affected_symbols,
            ),
            risk=ChangeRiskItem(
                score=review.risk.score,
                level=review.risk.level,
                reasons=review.risk.reasons,
            ),
            recommended_tests=review.recommended_tests,
            test_recommendations=[
                TestRecommendationItem(
                    test_target=t.test_target,
                    file_path=t.file_path,
                    reason=t.reason,
                    symbol_name=t.symbol_name,
                )
                for t in review.test_recommendations
            ],
            diff_stats=review.diff_stats,
            review_notes=review.review_notes,
            summary=review.summary,
        )
    except NotAGitRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reviewing Git changes: {str(e)}")


@router.post(
    "/review",
    response_model=ReviewChangeResponse,
    summary="Review Current Git Changes (POST)",
    description="Inspects working tree status, diff, changed symbols, impact, recommended tests, and scores risk.",
)
def review_code_change_post(
    request: ReviewChangeRequest,
) -> ReviewChangeResponse:
    return _run_change_review(project_dir=request.project_dir)


@router.get(
    "/review",
    response_model=ReviewChangeResponse,
    summary="Review Current Git Changes (GET)",
    description="Inspects working tree status, diff, changed symbols, impact, recommended tests, and scores risk.",
)
def review_code_change_get(
    project_dir: str = Query(".", description="Target project directory"),
) -> ReviewChangeResponse:
    return _run_change_review(project_dir=project_dir)


def _run_git_intelligence(project_dir: str) -> GitChangeSummaryResponse:
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project directory does not exist: '{project_dir}'",
        )

    try:
        from app.changes.git_intelligence import GitChangeIntelligenceService

        service = GitChangeIntelligenceService(project_root=root)
        summary = service.analyze_working_tree()

        return GitChangeSummaryResponse(
            branch=summary.branch,
            changed_files=[
                GitChangeItem(
                    file_path=cf.file_path,
                    change_type=cf.change_type,
                    staged=cf.staged,
                    unstaged=cf.unstaged,
                    additions=cf.additions,
                    deletions=cf.deletions,
                    diff=cf.diff,
                )
                for cf in summary.changed_files
            ],
            changed_symbols=summary.changed_symbols,
            impacted_symbols=summary.impacted_symbols,
            impacted_files=summary.impacted_files,
            relevant_tests=summary.relevant_tests,
            risk=summary.risk,
            risk_reason=summary.risk_reason,
            warnings=summary.warnings,
        )
    except NotAGitRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing Git changes: {str(e)}")


@router.get(
    "/git-intelligence",
    response_model=GitChangeSummaryResponse,
    summary="Git-Aware Change Intelligence (GET)",
    description="Inspects working tree changes, symbols, blast radius, tests, and risk for uncommitted changes.",
)
def git_intelligence_get(
    project_dir: str = Query(".", description="Target project directory"),
) -> GitChangeSummaryResponse:
    return _run_git_intelligence(project_dir=project_dir)


def _run_autonomous_fix(request: str, mode: str, force: bool, project_dir: str) -> AutonomousFixResponse:
    if not request or not request.strip():
        raise HTTPException(status_code=400, detail="Change request cannot be empty.")

    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    try:
        from app.changes.autonomous_fix import AutonomousFixService
        from app.changes.models import FixMode

        service = AutonomousFixService(project_root=root)
        fix_mode = FixMode(mode.upper()) if mode else FixMode.PLAN
        res = service.execute(request=request.strip(), mode=fix_mode, force=force)

        return AutonomousFixResponse(
            mode=res.mode.value if isinstance(res.mode, FixMode) else str(res.mode),
            status=res.status,
            request=res.request,
            phase=res.phase,
            applied=res.applied,
            errors=res.errors,
            warnings=res.warnings,
            message=res.message,
            data=res.to_dict(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing autonomous fix: {str(e)}")


@router.post(
    "/fix",
    response_model=AutonomousFixResponse,
    summary="Autonomous Code Fix Loop (POST)",
    description="Coordinates the autonomous fix loop across PLAN, PATCH, and AUTO modes.",
)
def autonomous_fix_post(
    request: AutonomousFixRequest,
) -> AutonomousFixResponse:
    return _run_autonomous_fix(
        request=request.request,
        mode=request.mode,
        force=request.force,
        project_dir=request.project_dir,
    )


@router.get(
    "/fix",
    response_model=AutonomousFixResponse,
    summary="Autonomous Code Fix Loop (GET)",
    description="Coordinates the autonomous fix loop across PLAN, PATCH, and AUTO modes.",
)
def autonomous_fix_get(
    request: str = Query(..., min_length=1, description="Developer fix or refactoring request"),
    mode: str = Query("plan", description="Fix execution mode: 'plan', 'patch', or 'auto'"),
    force: bool = Query(False, description="Force execution even if working tree is dirty"),
    project_dir: str = Query(".", description="Target project directory"),
) -> AutonomousFixResponse:
    return _run_autonomous_fix(
        request=request,
        mode=mode,
        force=force,
        project_dir=project_dir,
    )


def _run_change_proposal(request: str, project_dir: str) -> ChangeProposalResponse:
    if not request or not request.strip():
        raise HTTPException(status_code=400, detail="Change request cannot be empty.")

    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    try:
        from app.changes.proposal_generator import ChangeProposalGenerator

        generator = ChangeProposalGenerator(project_root=root)
        proposal = generator.propose(change_request=request.strip())

        return ChangeProposalResponse(
            proposal_id=proposal.proposal_id,
            request=proposal.request,
            target_symbol=proposal.target_symbol,
            target_file=proposal.target_file,
            target_lines=proposal.target_lines,
            change_summary=proposal.change_summary,
            affected_files=proposal.affected_files,
            affected_symbols=proposal.affected_symbols,
            proposed_changes=proposal.proposed_changes,
            patch=proposal.patch,
            tests_to_update=proposal.tests_to_update,
            tests_to_add=proposal.tests_to_add,
            risk=proposal.risk,
            reasoning=proposal.reasoning,
            confidence=proposal.confidence,
            warnings=proposal.warnings,
            unverified_assumptions=proposal.unverified_assumptions,
            status=proposal.status,
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
            approved_at=proposal.approved_at,
            rejected_at=proposal.rejected_at,
            applied_at=proposal.applied_at,
            decision=proposal.decision,
            decision_reason=proposal.decision_reason,
            target_content_hash=proposal.target_content_hash,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating change proposal: {str(e)}")


@router.post(
    "/propose",
    response_model=ChangeProposalResponse,
    summary="Generate Intelligent Change Proposal (POST)",
    description="Analyzes change request, resolves target, generates reviewable unified diff patch and risk assessment without modifying files.",
)
def propose_change_post(
    request: ChangeProposalRequest,
) -> ChangeProposalResponse:
    return _run_change_proposal(
        request=request.request,
        project_dir=request.project_dir,
    )


@router.get(
    "/propose",
    response_model=ChangeProposalResponse,
    summary="Generate Intelligent Change Proposal (GET)",
    description="Analyzes change request, resolves target, generates reviewable unified diff patch and risk assessment without modifying files.",
)
def propose_change_get(
    request: str = Query(..., min_length=1, description="Developer natural language change request"),
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeProposalResponse:
    return _run_change_proposal(
        request=request,
        project_dir=project_dir,
    )


@router.get(
    "/proposals/{proposal_id}",
    response_model=ChangeProposalResponse,
    summary="Inspect Change Proposal by ID (GET)",
    description="Retrieves a change proposal, diff patch, risk assessment, and approval status.",
)
def get_proposal_by_id(
    proposal_id: str,
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeProposalResponse:
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    from app.changes.approval import ApprovalService, ProposalNotFoundError

    service = ApprovalService(project_root=root)
    try:
        prop = service.get_proposal(proposal_id)
        return ChangeProposalResponse(**prop.to_dict())
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving proposal: {e}")


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ChangeProposalResponse,
    summary="Approve Change Proposal (POST)",
    description="Approves a pending change proposal with validation checks and human-in-the-loop safety.",
)
def approve_proposal_post(
    proposal_id: str,
    body: Optional[ApproveProposalRequest] = None,
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeProposalResponse:
    target_dir = body.project_dir if body else project_dir
    root = Path(target_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{target_dir}'")

    from app.changes.approval import (
        AlreadyAppliedError,
        ApprovalService,
        DuplicateApprovalError,
        HighRiskConfirmationError,
        ProposalNotFoundError,
        RejectedProposalError,
        StaleProposalError,
    )

    service = ApprovalService(project_root=root)
    try:
        reason = body.reason if body else None
        force = body.force if body else False
        prop = service.approve_proposal(proposal_id=proposal_id, reason=reason, force=force)
        return ChangeProposalResponse(**prop.to_dict())
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (DuplicateApprovalError, RejectedProposalError, AlreadyAppliedError, StaleProposalError, HighRiskConfirmationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving proposal: {e}")


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ChangeProposalResponse,
    summary="Reject Change Proposal (POST)",
    description="Rejects a pending change proposal.",
)
def reject_proposal_post(
    proposal_id: str,
    body: Optional[RejectProposalRequest] = None,
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeProposalResponse:
    target_dir = body.project_dir if body else project_dir
    root = Path(target_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{target_dir}'")

    from app.changes.approval import (
        AlreadyAppliedError,
        ApprovalService,
        ProposalNotFoundError,
    )

    service = ApprovalService(project_root=root)
    try:
        reason = body.reason if body else None
        prop = service.reject_proposal(proposal_id=proposal_id, reason=reason)
        return ChangeProposalResponse(**prop.to_dict())
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AlreadyAppliedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rejecting proposal: {e}")


def _run_execute_proposal(
    proposal_id: str,
    body: Optional[ExecuteProposalRequest] = None,
    project_dir: str = ".",
) -> ChangeExecutionResponse:
    target_dir = body.project_dir if body else project_dir
    root = Path(target_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{target_dir}'")

    from app.changes.approval import (
        AlreadyAppliedError,
        ProposalNotFoundError,
        RejectedProposalError,
    )
    from app.changes.executor import (
        ChangeExecutor,
        InvalidPatchError,
        StalePatchError,
        UnapprovedProposalError,
    )

    executor = ChangeExecutor(project_root=root)
    try:
        run_tests = body.run_tests if body else True
        execution = executor.execute(proposal_id=proposal_id, run_tests=run_tests)
        return ChangeExecutionResponse(**execution.to_dict())
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (UnapprovedProposalError, AlreadyAppliedError, RejectedProposalError, StalePatchError, InvalidPatchError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing change proposal: {e}")


@router.post(
    "/{proposal_id}/execute",
    response_model=ChangeExecutionResponse,
    summary="Execute Approved Change Proposal (POST)",
    description="Safely executes an approved change proposal with pre-flight checks, patch application, tests, and automatic rollback.",
)
def execute_proposal_root_post(
    proposal_id: str,
    body: Optional[ExecuteProposalRequest] = None,
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeExecutionResponse:
    return _run_execute_proposal(proposal_id=proposal_id, body=body, project_dir=project_dir)


@router.post(
    "/proposals/{proposal_id}/execute",
    response_model=ChangeExecutionResponse,
    summary="Execute Approved Change Proposal by ID (POST)",
    description="Safely executes an approved change proposal with pre-flight checks, patch application, tests, and automatic rollback.",
)
def execute_proposal_post(
    proposal_id: str,
    body: Optional[ExecuteProposalRequest] = None,
    project_dir: str = Query(".", description="Target project directory"),
) -> ChangeExecutionResponse:
    return _run_execute_proposal(proposal_id=proposal_id, body=body, project_dir=project_dir)


def _run_fix_loop(
    request: str,
    mode: str = "plan",
    max_iterations: int = 3,
    force: bool = False,
    proposal_id: Optional[str] = None,
    project_dir: str = ".",
) -> FixLoopResponse:
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{project_dir}'")

    from app.changes.fix_loop import FixLoopService

    try:
        service = FixLoopService(project_root=root)
        result = service.fix(
            request=request,
            mode=mode,
            max_iterations=max_iterations,
            force=force,
            proposal_id=proposal_id,
        )
        return FixLoopResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing autonomous fix loop: {e}")


@router.post(
    "/fix-loop",
    response_model=FixLoopResponse,
    summary="Autonomous Fix Loop (POST)",
    description="Executes a controlled, Git-aware autonomous repair loop with iterative failure analysis, patch synthesis, test verification, and safe rollback.",
)
def fix_loop_post(
    body: FixLoopRequest,
) -> FixLoopResponse:
    return _run_fix_loop(
        request=body.request,
        mode=body.mode,
        max_iterations=body.max_iterations,
        force=body.force,
        proposal_id=body.proposal_id,
        project_dir=body.project_dir,
    )





