"""
DevPilot Task Management REST API Endpoints (v3.4).

Exposes autonomous issue-to-PR task lifecycle endpoints:
creation, analysis, planning, approval, rejection, execution, test verification,
diff inspection, rollback, and PR report generation.
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.tasks import (
    ApproveTaskRequest,
    CreateTaskRequest,
    ExecuteTaskRequest,
    RejectTaskRequest,
    TaskListResponse,
    TaskReportResponse,
    TaskResponse,
)
from app.tasks.engine import EngineeringTaskEngine
from app.tasks.models import InvalidTaskStateTransitionError
from app.tasks.store import TaskStore

router = APIRouter(tags=["Task Engineering (v3.4)"])


def _get_engine(project_root: Optional[str] = None) -> EngineeringTaskEngine:
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    return EngineeringTaskEngine(project_root=root)


def _get_store(project_root: Optional[str] = None) -> TaskStore:
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    return TaskStore(project_root=root)


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Engineering Task",
    description="Initializes a new issue-to-PR autonomous engineering task.",
)
def create_task(req: CreateTaskRequest) -> TaskResponse:
    engine = _get_engine()
    task = engine.create_task(
        title=req.title,
        description=req.description or "",
        task_type=req.task_type,
        priority=req.priority,
        project_id=req.project_id or "default",
    )
    return TaskResponse(task=task.to_dict())


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="List Engineering Tasks",
    description="Lists existing engineering tasks with optional status and priority filters.",
)
def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status (CREATED, ANALYZED, PLANNED, APPROVED, COMPLETED, etc.)"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
) -> TaskListResponse:
    store = _get_store()
    tasks = store.list_tasks(status=status, task_type=task_type, priority=priority)
    return TaskListResponse(total=len(tasks), tasks=[t.to_dict() for t in tasks])


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get Engineering Task",
    description="Retrieves full task details, analysis, root cause, plan, and PR summary.",
)
def get_task(task_id: str) -> TaskResponse:
    store = _get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return TaskResponse(task=task.to_dict())


@router.post(
    "/tasks/{task_id}/analyze",
    response_model=TaskResponse,
    summary="Analyze Task & Root Cause",
    description="Performs codebase analysis, symbol resolution, and root cause evidence discovery.",
)
def analyze_task(task_id: str) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.analyze_task(task_id)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post(
    "/tasks/{task_id}/plan",
    response_model=TaskResponse,
    summary="Generate Implementation Plan & Patch",
    description="Constructs step-by-step implementation plan and reviewable patch proposal.",
)
def plan_task(task_id: str) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.plan_task(task_id)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}")


@router.post(
    "/tasks/{task_id}/approve",
    response_model=TaskResponse,
    summary="Approve Engineering Task",
    description="Approves task and authorizes safe patch execution.",
)
def approve_task(task_id: str, req: ApproveTaskRequest) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.approve_task(task_id, reason=req.reason, force=req.force)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@router.post(
    "/tasks/{task_id}/reject",
    response_model=TaskResponse,
    summary="Reject Engineering Task",
    description="Rejects task and records developer decision.",
)
def reject_task(task_id: str, req: RejectTaskRequest) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.reject_task(task_id, reason=req.reason)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rejection failed: {str(e)}")


@router.post(
    "/tasks/{task_id}/execute",
    response_model=TaskResponse,
    summary="Execute Approved Task",
    description="Executes approved task with safety checkpoints, syntax verification, test verification, and post-review.",
)
def execute_task(task_id: str, req: ExecuteTaskRequest) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.execute_task(task_id, run_tests=req.run_tests)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.post(
    "/tasks/{task_id}/rollback",
    response_model=TaskResponse,
    summary="Rollback Task",
    description="Reverts task changes from backup checkpoint.",
)
def rollback_task(task_id: str) -> TaskResponse:
    engine = _get_engine()
    try:
        task = engine.rollback_task(task_id)
        return TaskResponse(task=task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTaskStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.get(
    "/tasks/{task_id}/diff",
    summary="Get Task Diff",
    description="Retrieves the proposed or executed unified diff for a task.",
)
def get_task_diff(task_id: str):
    store = _get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return {"success": True, "task_id": task_id, "patch": task.patch or ""}


@router.get(
    "/tasks/{task_id}/report",
    response_model=TaskReportResponse,
    summary="Get Task PR Report",
    description="Retrieves the PR-ready markdown package for a task.",
)
def get_task_report(task_id: str) -> TaskReportResponse:
    store = _get_store()
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return TaskReportResponse(
        task_id=task.task_id,
        title=task.title,
        status=task.status,
        pr_summary=task.pr_summary or "(PR summary pending completion)",
    )
