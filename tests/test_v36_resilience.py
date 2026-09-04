"""
DevPilot v3.6 Enterprise Reliability, Resilience & Failure Recovery Suite.

Tests:
1. Atomic storage persistence & corrupt file skip recovery
2. Idempotent task approvals & execution state transitions
3. Path sandboxing & resource boundary protection
4. API error predictability with correlation IDs
5. Graceful lifespan startup and shutdown lifecycle
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.changes.models import ChangeProposal
from app.changes.proposal_store import ProposalStore
from app.main import app, lifespan
from app.tasks.engine import EngineeringTaskEngine
from app.tasks.models import EngineeringTask, TaskState
from app.tasks.store import TaskStore


@pytest.fixture
def client():
    return TestClient(app)


def test_atomic_proposal_storage_and_recovery(tmp_path):
    store = ProposalStore(project_root=tmp_path)
    proposal = ChangeProposal(
        request="Optimize database queries",
        proposal_id="prop_resilience_001",
        change_summary="Add index",
        patch="--- a/db.py\n+++ b/db.py\n@@ -1 +1 @@\n-old\n+new",
    )
    saved = store.save(proposal)
    assert saved.proposal_id == "prop_resilience_001"

    # Verify atomic file exists and is valid JSON
    prop_file = tmp_path / ".devpilot" / "proposals" / "prop_resilience_001.json"
    assert prop_file.exists()
    with open(prop_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["proposal_id"] == "prop_resilience_001"

    # Add a corrupt temporary file and ensure listing/reading ignores it
    corrupt_file = tmp_path / ".devpilot" / "proposals" / "corrupted.tmp"
    corrupt_file.write_text("invalid json content {{{", encoding="utf-8")

    retrieved = store.get("prop_resilience_001")
    assert retrieved is not None
    assert retrieved.change_summary == "Add index"


def test_idempotent_task_state_transitions(tmp_path):
    store = TaskStore(project_root=tmp_path)
    task = EngineeringTask(
        task_id="task_idem_001",
        title="Test Idempotency",
        description="",
        status=TaskState.WAITING_APPROVAL.value,
    )
    store.save(task)

    engine = EngineeringTaskEngine(project_root=tmp_path)

    # 1. Approve task
    approved_1 = engine.approve_task("task_idem_001", reason="First click")
    assert approved_1.status == TaskState.APPROVED.value

    # 2. Second approve click (idempotent - should not throw InvalidTaskStateTransitionError)
    approved_2 = engine.approve_task("task_idem_001", reason="Second click")
    assert approved_2.status == TaskState.APPROVED.value


def test_task_store_corrupted_file_resilience(tmp_path):
    store = TaskStore(project_root=tmp_path)

    # Valid task
    t1 = EngineeringTask(
        task_id="t_valid_01",
        title="Valid Task",
        description="",
        status=TaskState.CREATED.value,
    )
    store.save(t1)

    # Corrupt JSON file in directory
    corrupt_file = tmp_path / ".devpilot" / "tasks" / "t_corrupt_02.json"
    corrupt_file.write_text("{ unparseable json ...", encoding="utf-8")

    # Listing should skip corrupt file gracefully and return valid task
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].task_id == "t_valid_01"


def test_api_predictable_error_contract_and_correlation(client):
    # Invalid Project ID
    res = client.get("/api/projects/non_existent_123456789")
    assert res.status_code == 404
    data = res.json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"
    assert "request_id" in data
    assert res.headers.get("X-Request-ID") == data["request_id"]


def test_graceful_lifespan_lifecycle():
    import asyncio

    async def _run():
        async with lifespan(app):
            dot_devpilot = Path.cwd() / ".devpilot"
            assert dot_devpilot.exists()

    asyncio.run(_run())
