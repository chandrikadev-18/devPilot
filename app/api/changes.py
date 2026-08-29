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
    ChangedSymbolItem,
    ChangeImpactItem,
    ChangePlanEvidenceItem,
    ChangeRiskItem,
    GitStatusSummaryItem,
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

