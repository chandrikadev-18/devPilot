"""
DevPilot Git Intelligence API Router.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Path as FastApiPath, Query

from app.git.history import (
    get_blame_for_symbol,
    get_commit_detail,
    get_history_for_symbol,
    get_last_change_for_symbol,
)
from app.git.repository import (
    GitBlameError,
    GitCommitNotFoundError,
    GitError,
    GitFileNotFoundError,
    GitRepository,
    NotAGitRepositoryError,
    get_repository,
)
from app.schemas.git import (
    GitBlameResponse,
    GitCommitDetailResponse,
    GitHistoryResponse,
    GitLastChangeResponse,
)

router = APIRouter(prefix="/git", tags=["Git Intelligence"])


def _get_repo(project_dir: str = ".") -> GitRepository:
    """Helper to resolve GitRepository safely."""
    root = Path(project_dir).resolve()
    if not root.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project directory does not exist: '{project_dir}'",
        )
    try:
        return get_repository(root)
    except NotAGitRepositoryError:
        raise HTTPException(
            status_code=400,
            detail=f"Directory is not a Git repository: '{project_dir}'",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error accessing Git repository: {str(e)}",
        )


@router.get(
    "/last-change",
    response_model=GitLastChangeResponse,
    summary="Get Last Change for Symbol or File",
    description="Finds the most recent Git commit, author, date, and commit message affecting a symbol or file.",
)
def get_symbol_last_change(
    symbol: str = Query(..., min_length=1, description="Symbol name (e.g. 'GraphBuilder.build') or file path"),
    project_dir: str = Query(".", description="Target codebase directory"),
) -> GitLastChangeResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")

    repo = _get_repo(project_dir)
    try:
        res = get_last_change_for_symbol(repo=repo, symbol=symbol.strip())
        return GitLastChangeResponse(**res.to_dict())
    except GitFileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (GitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving last change: {str(e)}")


@router.get(
    "/history",
    response_model=GitHistoryResponse,
    summary="Get Commit History for Symbol or File",
    description="Retrieves chronological Git commit history affecting a specific symbol or file.",
)
def get_symbol_history(
    symbol: str = Query(..., min_length=1, description="Symbol name or file path"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of commits to retrieve"),
    project_dir: str = Query(".", description="Target codebase directory"),
) -> GitHistoryResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")

    repo = _get_repo(project_dir)
    try:
        data = get_history_for_symbol(repo=repo, symbol=symbol.strip(), limit=limit)
        return GitHistoryResponse(**data)
    except GitFileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (GitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")


@router.get(
    "/blame",
    response_model=GitBlameResponse,
    summary="Get Git Blame Analysis for Symbol or File",
    description="Performs line-level Git blame analysis targeted at a symbol definition or file.",
)
def get_symbol_blame(
    symbol: str = Query(..., min_length=1, description="Symbol name or file path"),
    start_line: Optional[int] = Query(None, ge=1, description="Optional starting line number"),
    end_line: Optional[int] = Query(None, ge=1, description="Optional ending line number"),
    project_dir: str = Query(".", description="Target codebase directory"),
) -> GitBlameResponse:
    if not symbol or not symbol.strip():
        raise HTTPException(status_code=400, detail="Symbol parameter cannot be empty.")

    if start_line is not None and end_line is not None and end_line < start_line:
        raise HTTPException(status_code=400, detail=f"end_line ({end_line}) cannot be less than start_line ({start_line}).")

    repo = _get_repo(project_dir)
    try:
        data = get_blame_for_symbol(
            repo=repo,
            symbol=symbol.strip(),
            start_line=start_line,
            end_line=end_line,
        )
        return GitBlameResponse(**data)
    except GitFileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (GitBlameError, GitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error performing blame: {str(e)}")


@router.get(
    "/commit/{commit}",
    response_model=GitCommitDetailResponse,
    summary="Inspect Specific Commit",
    description="Retrieves metadata, statistics, and diff summary for a specific commit hash or revision.",
)
def get_commit(
    commit: str = FastApiPath(..., description="Commit SHA or revision (e.g. HEAD)"),
    project_dir: str = Query(".", description="Target codebase directory"),
) -> GitCommitDetailResponse:
    if not commit or not commit.strip():
        raise HTTPException(status_code=400, detail="Commit parameter cannot be empty.")

    repo = _get_repo(project_dir)
    try:
        detail = get_commit_detail(repo=repo, commit_hash=commit.strip())
        return GitCommitDetailResponse(**detail.to_dict())
    except GitCommitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (GitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inspecting commit: {str(e)}")
