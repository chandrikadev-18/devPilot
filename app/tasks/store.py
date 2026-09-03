"""
DevPilot Task Persistence Store (v3.4).

Manages storage, retrieval, status filtering, and updates for EngineeringTask objects.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from app.tasks.models import EngineeringTask, TaskState


class TaskStore:
    """
    Persists EngineeringTask objects in `.devpilot/tasks/` or `data/tasks/`.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.tasks_dir = self.project_root / ".devpilot" / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, task_id: str) -> Path:
        safe_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))
        return self.tasks_dir / f"{safe_id}.json"

    def save(self, task: EngineeringTask) -> None:
        """Saves a task to disk atomically."""
        path = self._get_path(task.task_id)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, indent=2)
        temp_path.replace(path)

    def get(self, task_id: str) -> Optional[EngineeringTask]:
        """Retrieves a task by ID."""
        path = self._get_path(task_id)
        if not path.exists():
            # Try secondary data directory
            sec_path = self.project_root / "data" / "tasks" / f"{task_id}.json"
            if sec_path.exists():
                path = sec_path
            else:
                return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return EngineeringTask.from_dict(data)
        except Exception:
            return None

    def list_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[EngineeringTask]:
        """Lists all tasks with optional filtering."""
        tasks: List[EngineeringTask] = []
        if not self.tasks_dir.exists():
            return tasks

        for path in sorted(self.tasks_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.name.endswith(".tmp"):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                task = EngineeringTask.from_dict(data)

                if status and task.status != status:
                    continue
                if task_type and task.task_type != task_type:
                    continue
                if priority and task.priority != priority:
                    continue

                tasks.append(task)
            except Exception:
                continue

        return tasks

    def delete(self, task_id: str) -> bool:
        """Deletes a task by ID."""
        path = self._get_path(task_id)
        if path.exists():
            path.unlink()
            return True
        return False
