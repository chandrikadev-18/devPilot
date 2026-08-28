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
    ChangeRiskItem,
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
