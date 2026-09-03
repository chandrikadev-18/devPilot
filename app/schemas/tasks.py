"""
DevPilot Task API Schemas (v3.4).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    title: str = Field(..., description="Title of the issue or engineering task")
    description: Optional[str] = Field(default="", description="Detailed description or error traceback")
    task_type: Optional[str] = Field(default=None, description="Task type: bug, feature, refactor, performance, security, test, documentation")
    priority: Optional[str] = Field(default=None, description="Task priority: LOW, MEDIUM, HIGH, CRITICAL")
    project_id: Optional[str] = Field(default="default", description="Associated project ID")


class ApproveTaskRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Approval reason or reviewer comment")
    force: bool = Field(default=False, description="Force approval for high risk tasks")


class RejectTaskRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Rejection reason")


class ExecuteTaskRequest(BaseModel):
    run_tests: bool = Field(default=True, description="Whether to run tests after applying changes")


class TaskResponse(BaseModel):
    success: bool = True
    task: Dict[str, Any]


class TaskListResponse(BaseModel):
    success: bool = True
    total: int
    tasks: List[Dict[str, Any]]


class TaskReportResponse(BaseModel):
    success: bool = True
    task_id: str
    title: str
    status: str
    pr_summary: Optional[str] = None
