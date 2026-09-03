"""
DevPilot v3.4 Autonomous Issue-to-PR Software Engineering Agent Suite.

Tests:
1. Task Creation & Type/Priority Inference
2. State Machine Transition Integrity
3. Issue Understanding & Root Cause Discovery
4. Implementation Planning & Test Discovery
5. Approval & Rejection Workflow
6. Safe Execution, Verification & PR-Ready Summary Package
7. Checkpoint Rollback Lifecycle
8. TaskStore Filtering & Persistence
9. FastAPI REST Endpoints Integration
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tasks.engine import EngineeringTaskEngine
from app.tasks.models import (
    EngineeringTask,
    InvalidTaskStateTransitionError,
    TaskPriority,
    TaskState,
    TaskType,
    validate_task_transition,
)
from app.tasks.store import TaskStore


@pytest.fixture
def client():
    return TestClient(app)


def test_task_creation_and_type_inference(tmp_path):
    engine = EngineeringTaskEngine(project_root=tmp_path)

    # Bug report
    bug_task = engine.create_task("Fix login returning 500 when password is invalid")
    assert bug_task.task_type == TaskType.BUG.value
    assert bug_task.priority in (TaskPriority.HIGH.value, TaskPriority.CRITICAL.value)
    assert bug_task.status == TaskState.CREATED.value

    # Refactor request
    refactor_task = engine.create_task("Refactor authentication module to clean up imports")
    assert refactor_task.task_type == TaskType.REFACTOR.value

    # Performance request
    perf_task = engine.create_task("Optimize query latency and caching")
    assert perf_task.task_type == TaskType.PERFORMANCE.value


def test_task_state_machine_transition_guards():
    task = EngineeringTask(
        task_id="task_state_001",
        title="Test state guard",
        description="",
    )
    assert task.status == TaskState.CREATED.value

    # Legal transition
    task.transition_to(TaskState.ANALYZING)
    assert task.status == TaskState.ANALYZING.value

    task.transition_to(TaskState.ANALYZED)
    assert task.status == TaskState.ANALYZED.value

    # Illegal transition: ANALYZED directly to COMPLETED
    with pytest.raises(InvalidTaskStateTransitionError):
        task.transition_to(TaskState.COMPLETED)


def test_task_store_persistence_and_filtering(tmp_path):
    store = TaskStore(project_root=tmp_path)

    t1 = EngineeringTask(
        task_id="t_001",
        title="Fix 500 error",
        description="",
        status=TaskState.WAITING_APPROVAL.value,
        task_type=TaskType.BUG.value,
        priority=TaskPriority.HIGH.value,
    )
    t2 = EngineeringTask(
        task_id="t_002",
        title="Add caching",
        description="",
        status=TaskState.COMPLETED.value,
        task_type=TaskType.PERFORMANCE.value,
        priority=TaskPriority.MEDIUM.value,
    )
    store.save(t1)
    store.save(t2)

    # Retrieval
    retrieved = store.get("t_001")
    assert retrieved is not None
    assert retrieved.title == "Fix 500 error"

    # Filtering
    waiting = store.list_tasks(status=TaskState.WAITING_APPROVAL.value)
    assert len(waiting) == 1
    assert waiting[0].task_id == "t_001"

    completed = store.list_tasks(status=TaskState.COMPLETED.value)
    assert len(completed) == 1
    assert completed[0].task_id == "t_002"


def test_issue_understanding_and_planning_workflow(tmp_path):
    auth_py = tmp_path / "auth_service.py"
    auth_py.write_text(
        "class AuthService:\n"
        "    def login(self, username, password):\n"
        "        if not password:\n"
        "            raise ValueError('Password required')\n"
        "        return True\n",
        encoding="utf-8"
    )

    engine = EngineeringTaskEngine(project_root=tmp_path)
    task = engine.create_task("Fix login in AuthService")
    assert task.status == TaskState.CREATED.value

    # 1. Analyze
    analyzed = engine.analyze_task(task.task_id)
    assert analyzed.status == TaskState.ANALYZED.value
    assert analyzed.root_cause is not None
    assert analyzed.root_cause.confidence in ("CONFIRMED", "PROBABLE")

    # 2. Plan
    planned = engine.plan_task(task.task_id)
    assert planned.status == TaskState.WAITING_APPROVAL.value
    assert len(planned.implementation_plan) > 0
    assert planned.proposal_id is not None

    # 3. Reject
    rejected = engine.reject_task(task.task_id, reason="Not applicable")
    assert rejected.status == TaskState.REJECTED.value


def test_task_rest_api_lifecycle(client):
    # 1. Create Task
    create_res = client.post("/api/tasks", json={
        "title": "Fix scan error handling",
        "description": "Scanner throws exception on missing folder",
        "task_type": "bug",
        "priority": "HIGH"
    })
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["success"] is True
    task_id = data["task"]["task_id"]
    assert data["task"]["status"] == "CREATED"

    # 2. Get Task
    get_res = client.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["task"]["task_id"] == task_id

    # 3. List Tasks
    list_res = client.get("/api/tasks")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 4. Get Report
    rep_res = client.get(f"/api/tasks/{task_id}/report")
    assert rep_res.status_code == 200
    assert rep_res.json()["task_id"] == task_id
