"""
DevPilot Project & Operation Models (v2.5).

Defines core data structures for registered codebases, repositories,
and tracked operation lifecycles.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    ERROR = "ERROR"


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OperationType(str, Enum):
    SCAN = "scan"
    GRAPH_BUILD = "graph_build"
    REVIEW = "review"
    AGENT = "agent"
    CHANGE = "change"
    FIX_LOOP = "fix_loop"


def generate_project_id(name: str) -> str:
    """Generates a URL-friendly unique identifier for a project."""
    clean_name = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    clean_name = clean_name[:24] or "project"
    rand_suffix = uuid.uuid4().hex[:6]
    return f"proj_{clean_name}_{rand_suffix}"


def generate_operation_id(op_type: str) -> str:
    """Generates a timestamped unique identifier for an operation."""
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y%m%d_%H%M%S")
    rand_suffix = uuid.uuid4().hex[:6]
    clean_op = op_type.lower().replace("-", "_")
    return f"op_{clean_op}_{ts}_{rand_suffix}"


@dataclass
class Project:
    """
    Represents a registered codebase or repository managed by DevPilot.
    """
    project_id: str
    name: str
    path: str
    repository: Optional[str] = None
    default_branch: str = "main"
    status: str = ProjectStatus.ACTIVE.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "path": self.path,
            "repository": self.repository,
            "default_branch": self.default_branch,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    def to_formatted_text(self) -> str:
        lines = [
            f"Project: {self.name} ({self.project_id})",
            "────────────────────────────────────────",
            f"Status:         {self.status}",
            f"Path:           {self.path}",
            f"Repository:     {self.repository or 'None (Local Directory)'}",
            f"Default Branch: {self.default_branch}",
            f"Created At:     {self.created_at}",
            f"Updated At:     {self.updated_at}",
        ]
        if self.metadata:
            lines.append("Metadata:")
            for k, v in self.metadata.items():
                lines.append(f"  • {k}: {v}")
        return "\n".join(lines)


@dataclass
class Operation:
    """
    Represents a tracked execution or job against a registered project.
    """
    operation_id: str
    project_id: str
    operation_type: str
    status: str = OperationStatus.PENDING.value
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "project_id": self.project_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }

    def to_formatted_text(self) -> str:
        lines = [
            f"Operation: {self.operation_id}",
            "────────────────────────────────────────",
            f"Project:        {self.project_id}",
            f"Type:           {self.operation_type}",
            f"Status:         {self.status}",
            f"Started At:     {self.started_at}",
            f"Completed At:   {self.completed_at or 'In Progress'}",
        ]
        if self.error:
            lines.extend(["", f"Error: {self.error}"])
        return "\n".join(lines)
