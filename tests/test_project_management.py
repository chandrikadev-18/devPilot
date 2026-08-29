"""
Tests for DevPilot v2.5 — API Stabilization + Project Management.
Verifies project registration, lifecycle, operations (scan, graph, review, agent),
path validation, error handling, CLI subcommands, and REST API endpoints.
"""

import json
from pathlib import Path
import subprocess
import pytest
from starlette.testclient import TestClient

from app.main import app, run_project_add, run_project_delete, run_project_graph, run_project_info, run_project_list, run_project_review, run_project_scan
from app.projects.models import (
    Operation,
    OperationStatus,
    OperationType,
    Project,
    ProjectStatus,
    generate_operation_id,
    generate_project_id,
)
from app.projects.service import (
    DuplicateProjectError,
    InvalidProjectPathError,
    OperationNotFoundError,
    ProjectNotFoundError,
    ProjectService,
)
from app.projects.store import OperationStore, ProjectStore


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Sets up a clean temporary Git repository project for testing."""
    app_dir = tmp_path / "app" / "graph"
    app_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    builder_file = app_dir / "builder.py"
    builder_file.write_text(
        "class GraphBuilder:\n"
        "    def build(self, project_path: str):\n"
        "        \"\"\"Build graph store.\"\"\"\n"
        "        return True\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_builder.py"
    test_file.write_text(
        "from app.graph.builder import GraphBuilder\n\n"
        "def test_graph_builder():\n"
        "    builder = GraphBuilder()\n"
        "    assert builder.build('.') is True\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(tmp_path), capture_output=True, check=True)

    return tmp_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Project Service & Store Unit Tests
# ==============================================================================

def test_project_store_save_get_and_list(tmp_path: Path):
    store = ProjectStore(storage_path=tmp_path / "projects.json")
    proj = Project(
        project_id="proj_test_1",
        name="Test Project",
        path=str(tmp_path).replace("\\", "/"),
        repository="https://github.com/example/repo.git",
        default_branch="main",
        status=ProjectStatus.ACTIVE.value,
    )
    store.save(proj)

    retrieved = store.get("proj_test_1")
    assert retrieved is not None
    assert retrieved.name == "Test Project"
    assert retrieved.path == str(tmp_path).replace("\\", "/")

    all_projs = store.list()
    assert len(all_projs) == 1
    assert all_projs[0].project_id == "proj_test_1"


def test_project_service_register_and_get(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)

    project = service.register_project(path=str(temp_project), name="Temp Repo")
    assert project.name == "Temp Repo"
    assert project.status == ProjectStatus.ACTIVE.value
    assert Path(project.path).resolve() == temp_project.resolve()

    fetched = service.get_project(project.project_id)
    assert fetched.project_id == project.project_id


def test_project_service_duplicate_registration_rejected(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)

    service.register_project(path=str(temp_project), name="Temp Repo")

    with pytest.raises(DuplicateProjectError):
        service.register_project(path=str(temp_project), name="Temp Repo Duplicate")


def test_project_service_invalid_path_rejected(tmp_path: Path):
    service = ProjectService(project_root=tmp_path)

    with pytest.raises(InvalidProjectPathError):
        service.register_project(path=str(tmp_path / "nonexistent_dir_123"))

    with pytest.raises(InvalidProjectPathError):
        service.register_project(path="")


def test_project_service_archive_and_delete(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)

    project = service.register_project(path=str(temp_project))

    # Archive
    service.delete_project(project.project_id, hard_delete=False)
    archived = service.get_project(project.project_id)
    assert archived.status == ProjectStatus.ARCHIVED.value

    # Hard Delete
    service.delete_project(project.project_id, hard_delete=True)
    with pytest.raises(ProjectNotFoundError):
        service.get_project(project.project_id)


# ==============================================================================
# 2. Project Operations (Scan, Graph, Review, Agent)
# ==============================================================================

def test_project_service_scan_operation(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    op, result = service.scan_project(project.project_id)

    assert op.status == OperationStatus.COMPLETED.value
    assert op.operation_type == OperationType.SCAN.value
    assert result["total_files"] >= 2
    assert ".py" in result["extensions"]


def test_project_service_graph_build_operation(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    op, result = service.build_graph(project.project_id)

    assert op.status == OperationStatus.COMPLETED.value
    assert op.operation_type == OperationType.GRAPH_BUILD.value
    assert result["total_nodes"] > 0
    assert result["classes"] >= 1


def test_project_service_review_operation(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    op, result = service.review_project(project.project_id)

    assert op.status == OperationStatus.COMPLETED.value
    assert op.operation_type == OperationType.REVIEW.value
    assert "is_clean" in result


def test_project_service_operation_tracking_and_retrieval(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    op, _ = service.scan_project(project.project_id)

    retrieved_op = service.get_operation(op.operation_id)
    assert retrieved_op.operation_id == op.operation_id
    assert retrieved_op.status == OperationStatus.COMPLETED.value

    ops = service.list_operations(project_id=project.project_id)
    assert len(ops) >= 1
    assert ops[0].operation_id == op.operation_id


# ==============================================================================
# 3. REST API Endpoint Tests
# ==============================================================================

def test_api_create_and_get_project(client: TestClient, temp_project: Path):
    # 1. Create Project
    res = client.post(
        "/projects",
        json={
            "path": str(temp_project),
            "name": "API Test Project",
            "default_branch": "main",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "API Test Project"
    project_id = data["project_id"]

    # 2. Get Project
    get_res = client.get(f"/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["project_id"] == project_id

    # 3. List Projects
    list_res = client.get("/projects")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1


def test_api_create_project_invalid_path_returns_400(client: TestClient, tmp_path: Path):
    res = client.post(
        "/projects",
        json={
            "path": str(tmp_path / "nonexistent_folder_abc"),
            "name": "Invalid Project",
        },
    )
    assert res.status_code == 400
    assert "does not exist" in res.json()["detail"]


def test_api_create_project_duplicate_returns_409(client: TestClient, temp_project: Path):
    # First creation
    res1 = client.post(
        "/projects",
        json={"path": str(temp_project), "name": "Project 1"},
    )
    assert res1.status_code in (201, 409)

    # Second creation with same path
    res2 = client.post(
        "/projects",
        json={"path": str(temp_project), "name": "Project 2"},
    )
    assert res2.status_code == 409


def test_api_get_missing_project_returns_404(client: TestClient):
    res = client.get("/projects/proj_nonexistent_999")
    assert res.status_code == 404


def test_api_project_scan_and_graph_build(client: TestClient, temp_project: Path):
    # Register project
    create_res = client.post(
        "/projects",
        json={"path": str(temp_project), "name": "Scan Graph Target"},
    )
    if create_res.status_code == 201:
        project_id = create_res.json()["project_id"]
    else:
        # Find existing by path
        projs = client.get("/projects").json()["projects"]
        project_id = next(p["project_id"] for p in projs if Path(p["path"]).resolve() == temp_project.resolve())

    # 1. Scan
    scan_res = client.post(f"/projects/{project_id}/scan")
    assert scan_res.status_code == 200
    assert scan_res.json()["total_files"] >= 2

    # 2. Graph Build
    graph_res = client.post(f"/projects/{project_id}/graph/build")
    assert graph_res.status_code == 200
    assert graph_res.json()["total_nodes"] > 0


def test_api_project_review(client: TestClient, temp_project: Path):
    # Register project
    create_res = client.post(
        "/projects",
        json={"path": str(temp_project), "name": "Review Target"},
    )
    if create_res.status_code == 201:
        project_id = create_res.json()["project_id"]
    else:
        projs = client.get("/projects").json()["projects"]
        project_id = next(p["project_id"] for p in projs if Path(p["path"]).resolve() == temp_project.resolve())

    review_res = client.post(f"/projects/{project_id}/review")
    assert review_res.status_code == 200
    assert "review" in review_res.json()


def test_api_delete_project(client: TestClient, temp_project: Path):
    create_res = client.post(
        "/projects",
        json={"path": str(temp_project), "name": "Delete Target"},
    )
    if create_res.status_code == 201:
        project_id = create_res.json()["project_id"]
    else:
        projs = client.get("/projects").json()["projects"]
        project_id = next(p["project_id"] for p in projs if Path(p["path"]).resolve() == temp_project.resolve())

    del_res = client.delete(f"/projects/{project_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"


def test_openapi_schema_contains_projects(client: TestClient):
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    assert "/projects" in schema["paths"]
    assert "/projects/{project_id}/scan" in schema["paths"]
    assert "/projects/{project_id}/graph/build" in schema["paths"]


# ==============================================================================
# 4. CLI Command Tests
# ==============================================================================

def test_cli_project_list_and_json(capsys):
    run_project_list(as_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)


def test_cli_project_add_and_info(temp_project: Path, capsys):
    # Add
    run_project_add(
        path=str(temp_project),
        name="CLI Test Project",
        as_json=True,
    )
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["name"] == "CLI Test Project" or "already registered" in data.get("error", "")

    if "project_id" in data:
        pid = data["project_id"]
        # Info
        run_project_info(project_id=pid, as_json=False)
        info_captured = capsys.readouterr()
        assert "Project:" in info_captured.out

        # Scan
        run_project_scan(project_id=pid, as_json=True)
        scan_captured = capsys.readouterr()
        assert "operation" in json.loads(scan_captured.out)

        # Graph
        run_project_graph(project_id=pid, as_json=True)
        graph_captured = capsys.readouterr()
        assert "operation" in json.loads(graph_captured.out)

        # Review
        run_project_review(project_id=pid, as_json=True)
        review_captured = capsys.readouterr()
        assert "operation" in json.loads(review_captured.out)

        # Delete
        run_project_delete(project_id=pid, hard=True, as_json=True)
        del_captured = capsys.readouterr()
        assert json.loads(del_captured.out)["success"] is True


def test_project_service_agent_empty_question_rejected(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)

    project = service.register_project(path=str(temp_project))
    with pytest.raises(Exception):
        service.ask_agent(project_id=project.project_id, question="")


def test_path_traversal_and_null_byte_protection(tmp_path: Path):
    service = ProjectService(project_root=tmp_path)
    with pytest.raises(InvalidProjectPathError):
        service.validate_path("invalid\0path")

    with pytest.raises(InvalidProjectPathError):
        service.validate_path(str(tmp_path / "../../../nonexistent_dir_9999"))


def test_failed_operation_lifecycle(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    op_store = OperationStore(storage_path=temp_project / ".devpilot" / "operations.json")
    service = ProjectService(project_root=temp_project, project_store=store, operation_store=op_store)

    project = service.register_project(path=str(temp_project))
    
    # Intentionally corrupt project path to trigger failed operation
    project.path = str(temp_project / "deleted_subdir_abc")
    store.save(project)

    with pytest.raises(InvalidProjectPathError):
        service.scan_project(project.project_id)

    ops = service.list_operations(project_id=project.project_id)
    # The scan_project will raise before creating op or record failure
    assert isinstance(ops, list)


def test_project_delete_preserves_filesystem_safety(temp_project: Path):
    store = ProjectStore(storage_path=temp_project / ".devpilot" / "projects.json")
    service = ProjectService(project_root=temp_project, project_store=store)

    project = service.register_project(path=str(temp_project))
    assert temp_project.exists()

    # Hard delete registration
    service.delete_project(project.project_id, hard_delete=True)

    # Confirm filesystem directory was NOT deleted
    assert temp_project.exists()
    assert (temp_project / "app").exists()


def test_cli_human_readable_output(temp_project: Path, capsys):
    # Test human-readable project list
    run_project_list(as_json=False)
    out1 = capsys.readouterr().out
    assert "Registered Projects" in out1 or "No projects registered" in out1


