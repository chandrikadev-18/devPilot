"""
DevPilot Project & Operation Pydantic Schemas (v2.5).

Defines request/response contracts and standard response envelopes.
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standardized API success envelope."""
    status: str = Field(default="success", description="Response status (success)")
    data: T = Field(..., description="Response payload data")
    message: Optional[str] = Field(None, description="Optional informational message")


class ApiErrorDetail(BaseModel):
    """Standardized error details."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")


class ApiErrorResponse(BaseModel):
    """Standardized API error envelope."""
    status: str = Field(default="error", description="Response status (error)")
    error: ApiErrorDetail = Field(..., description="Error payload")


class CreateProjectRequest(BaseModel):
    name: Optional[str] = Field(None, description="Optional project name (defaults to folder name)")
    path: str = Field(..., min_length=1, description="Absolute or relative path to project codebase directory")
    repository: Optional[str] = Field(None, description="Optional remote Git repository URL")
    default_branch: str = Field(default="main", description="Default Git branch name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom project metadata")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(None, description="Updated project name")
    default_branch: Optional[str] = Field(None, description="Updated default Git branch")
    status: Optional[str] = Field(None, description="Updated project status (ACTIVE, ARCHIVED, ERROR)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata dictionary")


class ProjectResponse(BaseModel):
    project_id: str = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    path: str = Field(..., description="Normalized codebase directory path")
    repository: Optional[str] = Field(None, description="Git remote repository URL")
    default_branch: str = Field(default="main", description="Default branch")
    status: str = Field(..., description="Project status (ACTIVE, ARCHIVED, ERROR)")
    created_at: str = Field(..., description="Registration timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Project metadata")


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse] = Field(default_factory=list, description="List of registered projects")
    total: int = Field(..., description="Total number of projects matching query")


class OperationResponse(BaseModel):
    operation_id: str = Field(..., description="Unique operation identifier")
    project_id: str = Field(..., description="Associated project ID")
    operation_type: str = Field(..., description="Operation type (scan, graph_build, review, agent)")
    status: str = Field(..., description="Operation status (PENDING, RUNNING, COMPLETED, FAILED)")
    started_at: str = Field(..., description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    result: Optional[Dict[str, Any]] = Field(None, description="Operation result payload")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class OperationListResponse(BaseModel):
    operations: List[OperationResponse] = Field(default_factory=list, description="List of operations")
    total: int = Field(..., description="Total count")


class ProjectScanResponse(BaseModel):
    operation: OperationResponse = Field(..., description="Operation metadata")
    project_name: str = Field(..., description="Scanned project name")
    project_path: str = Field(..., description="Scanned project path")
    total_files: int = Field(..., description="Total file count")
    total_dirs: int = Field(..., description="Total directory count")
    extensions: Dict[str, int] = Field(default_factory=dict, description="File extensions breakdown")
    files_count: int = Field(..., description="Count of scanned source files")


class ProjectGraphBuildResponse(BaseModel):
    operation: OperationResponse = Field(..., description="Operation metadata")
    project_id: str = Field(..., description="Project ID")
    total_nodes: int = Field(..., description="Total graph nodes")
    total_edges: int = Field(..., description="Total graph edges")
    files: int = Field(..., description="Total files in graph")
    classes: int = Field(..., description="Total classes in graph")
    functions: int = Field(..., description="Total functions in graph")


class ProjectReviewResponse(BaseModel):
    operation: OperationResponse = Field(..., description="Operation metadata")
    review: Dict[str, Any] = Field(..., description="Working tree code review payload")


class ProjectAgentRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Developer query for the project agent")
    provider: Optional[str] = Field(None, description="LLM provider name")
    model: Optional[str] = Field(None, description="LLM model name")


class ProjectAgentResponse(BaseModel):
    operation: OperationResponse = Field(..., description="Operation metadata")
    project_id: str = Field(..., description="Target project ID")
    question: str = Field(..., description="Question asked")
    answer: str = Field(..., description="Agent answer")
    tool_calls: List[Any] = Field(default_factory=list, description="Tools invoked during processing")
    iterations: int = Field(default=1, description="Number of agent reasoning iterations")
