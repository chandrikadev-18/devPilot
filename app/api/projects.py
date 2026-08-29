"""
DevPilot Project Management REST API Endpoints (v2.5).

Exposes project registration, lifecycle management, and project-scoped operations
(scan, graph build, review, and AI agent queries).
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.projects.service import (
    DuplicateProjectError,
    InvalidProjectPathError,
    OperationNotFoundError,
    ProjectNotFoundError,
    ProjectService,
)
from app.schemas.projects import (
    ApiResponse,
    CreateProjectRequest,
    OperationListResponse,
    OperationResponse,
    ProjectAgentRequest,
    ProjectAgentResponse,
    ProjectGraphBuildResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectReviewResponse,
    ProjectScanResponse,
)

router = APIRouter(tags=["Project Management"])


def _get_service() -> ProjectService:
    return ProjectService()


# ==============================================================================
# 1. Project Registration & CRUD
# ==============================================================================

@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Project",
    description="Registers a new local codebase directory or Git repository into DevPilot.",
)
def create_project(req: CreateProjectRequest) -> ProjectResponse:
    service = _get_service()
    try:
        project = service.register_project(
            path=req.path,
            name=req.name,
            repository=req.repository,
            default_branch=req.default_branch,
            metadata=req.metadata,
        )
        return ProjectResponse(**project.to_dict())
    except InvalidProjectPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateProjectError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register project: {e}")


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List Registered Projects",
    description="Lists all codebases and repositories registered in DevPilot.",
)
def list_projects(
    status: Optional[str] = Query(None, description="Optional filter by project status (ACTIVE, ARCHIVED, ERROR)"),
) -> ProjectListResponse:
    service = _get_service()
    projects = service.list_projects(status=status)
    return ProjectListResponse(
        projects=[ProjectResponse(**p.to_dict()) for p in projects],
        total=len(projects),
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project Details",
    description="Retrieves metadata for a specific registered project by its unique ID.",
)
def get_project(project_id: str) -> ProjectResponse:
    service = _get_service()
    try:
        project = service.get_project(project_id)
        return ProjectResponse(**project.to_dict())
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve project: {e}")


@router.delete(
    "/projects/{project_id}",
    response_model=ApiResponse[dict],
    summary="Delete / Archive Project",
    description="Deletes or archives a project registration.",
)
def delete_project(
    project_id: str,
    hard: bool = Query(False, description="If true, permanently removes project registration; otherwise archives it"),
) -> ApiResponse[dict]:
    service = _get_service()
    try:
        success = service.delete_project(project_id, hard_delete=hard)
        action = "deleted" if hard else "archived"
        return ApiResponse(
            status="success",
            data={"project_id": project_id, "action": action, "success": success},
            message=f"Project '{project_id}' successfully {action}.",
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")


# ==============================================================================
# 2. Project-Scoped Operations
# ==============================================================================

@router.post(
    "/projects/{project_id}/scan",
    response_model=ProjectScanResponse,
    summary="Scan Project Files",
    description="Scans project files, directories, and extension metrics.",
)
def scan_project(project_id: str) -> ProjectScanResponse:
    service = _get_service()
    try:
        op, result = service.scan_project(project_id)
        return ProjectScanResponse(
            operation=OperationResponse(**op.to_dict()),
            project_name=result["project_name"],
            project_path=result["project_path"],
            total_files=result["total_files"],
            total_dirs=result["total_dirs"],
            extensions=result["extensions"],
            files_count=result["files_count"],
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidProjectPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan project: {e}")


@router.post(
    "/projects/{project_id}/graph/build",
    response_model=ProjectGraphBuildResponse,
    summary="Build Project Dependency Graph",
    description="Builds the full codebase AST dependency graph for the specified project.",
)
def build_project_graph(project_id: str) -> ProjectGraphBuildResponse:
    service = _get_service()
    try:
        op, result = service.build_graph(project_id)
        return ProjectGraphBuildResponse(
            operation=OperationResponse(**op.to_dict()),
            project_id=result["project_id"],
            total_nodes=result["total_nodes"],
            total_edges=result["total_edges"],
            files=result["files"],
            classes=result["classes"],
            functions=result["functions"],
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidProjectPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build project dependency graph: {e}")


@router.post(
    "/projects/{project_id}/review",
    response_model=ProjectReviewResponse,
    summary="Review Project Code Changes",
    description="Executes a read-only Git code review on the project working tree.",
)
def review_project(project_id: str) -> ProjectReviewResponse:
    service = _get_service()
    try:
        op, result = service.review_project(project_id)
        return ProjectReviewResponse(
            operation=OperationResponse(**op.to_dict()),
            review=result,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidProjectPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to review project: {e}")


@router.post(
    "/projects/{project_id}/agent",
    response_model=ProjectAgentResponse,
    summary="Ask Project AI Agent",
    description="Queries the AI codebase exploration agent scoped to the project.",
)
def ask_project_agent(project_id: str, req: ProjectAgentRequest) -> ProjectAgentResponse:
    service = _get_service()
    try:
        op, result = service.ask_agent(
            project_id=project_id,
            question=req.question,
            provider=req.provider,
            model=req.model,
        )
        return ProjectAgentResponse(
            operation=OperationResponse(**op.to_dict()),
            project_id=result["project_id"],
            question=result["question"],
            answer=result["answer"],
            tool_calls=result["tool_calls"],
            iterations=result["iterations"],
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidProjectPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")


# ==============================================================================
# 3. Operations Queries
# ==============================================================================

@router.get(
    "/projects/{project_id}/operations",
    response_model=OperationListResponse,
    summary="List Operations for Project",
    description="Retrieves all tracked operations executed against the specified project.",
)
def list_project_operations(project_id: str) -> OperationListResponse:
    service = _get_service()
    # Verify project exists
    try:
        service.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ops = service.list_operations(project_id=project_id)
    return OperationListResponse(
        operations=[OperationResponse(**op.to_dict()) for op in ops],
        total=len(ops),
    )


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResponse,
    summary="Get Operation Status",
    description="Retrieves status and results of a tracked operation by its ID.",
)
def get_operation(operation_id: str) -> OperationResponse:
    service = _get_service()
    try:
        op = service.get_operation(operation_id)
        return OperationResponse(**op.to_dict())
    except OperationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get operation: {e}")
