"""
DevPilot Project & Operation Persistence Store (v2.5).

Provides JSON-backed persistence for registered projects and tracked operation records.
"""

import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from app.projects.models import (
    Operation,
    OperationStatus,
    Project,
    ProjectStatus,
)


class ProjectStore:
    """
    Thread-safe JSON persistence store for DevPilot registered projects.
    """

    def __init__(self, project_root: Optional[Path] = None, storage_path: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        if storage_path:
            self.storage_file = Path(storage_path).resolve()
        else:
            self.storage_file = self.project_root / ".devpilot" / "projects.json"
        self._lock = threading.RLock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_file.exists():
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)

    def _load_all_raw(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_storage()
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_all_raw(self, data: Dict[str, Dict[str, Any]]) -> None:
        self._ensure_storage()
        temp_file = self.storage_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.storage_file)

    def save(self, project: Project) -> Project:
        with self._lock:
            data = self._load_all_raw()
            data[project.project_id] = project.to_dict()
            self._save_all_raw(data)
            return project

    def get(self, project_id: str) -> Optional[Project]:
        with self._lock:
            data = self._load_all_raw()
            item = data.get(project_id)
            if not item:
                return None
            return Project(**item)

    def get_by_path(self, path: str) -> Optional[Project]:
        with self._lock:
            norm_target = str(Path(path).resolve()).replace("\\", "/")
            for p in self.list():
                norm_p = str(Path(p.path).resolve()).replace("\\", "/")
                if norm_p == norm_target:
                    return p
            return None

    def list(self, status: Optional[str] = None) -> List[Project]:
        with self._lock:
            data = self._load_all_raw()
            projects = [Project(**item) for item in data.values()]
            if status:
                projects = [p for p in projects if p.status.upper() == status.upper()]
            return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def delete(self, project_id: str) -> bool:
        with self._lock:
            data = self._load_all_raw()
            if project_id in data:
                del data[project_id]
                self._save_all_raw(data)
                return True
            return False

    def archive(self, project_id: str) -> Optional[Project]:
        with self._lock:
            project = self.get(project_id)
            if not project:
                return None
            project.status = ProjectStatus.ARCHIVED.value
            return self.save(project)


class OperationStore:
    """
    Thread-safe JSON persistence store for tracked project operations.
    """

    def __init__(self, project_root: Optional[Path] = None, storage_path: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        if storage_path:
            self.storage_file = Path(storage_path).resolve()
        else:
            self.storage_file = self.project_root / ".devpilot" / "operations.json"
        self._lock = threading.RLock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_file.exists():
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)

    def _load_all_raw(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_storage()
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_all_raw(self, data: Dict[str, Dict[str, Any]]) -> None:
        self._ensure_storage()
        temp_file = self.storage_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.storage_file)

    def save(self, operation: Operation) -> Operation:
        with self._lock:
            data = self._load_all_raw()
            data[operation.operation_id] = operation.to_dict()
            self._save_all_raw(data)
            return operation

    def get(self, operation_id: str) -> Optional[Operation]:
        with self._lock:
            data = self._load_all_raw()
            item = data.get(operation_id)
            if not item:
                return None
            return Operation(**item)

    def list(self, project_id: Optional[str] = None) -> List[Operation]:
        with self._lock:
            data = self._load_all_raw()
            operations = [Operation(**item) for item in data.values()]
            if project_id:
                operations = [op for op in operations if op.project_id == project_id]
            return sorted(operations, key=lambda op: op.started_at, reverse=True)
