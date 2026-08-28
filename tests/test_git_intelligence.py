"""
Tests for DevPilot v1.6 Git Intelligence Layer.

Covers:
- Symbol location resolution
- get_last_change_for_symbol
- get_history_for_symbol
- get_blame_for_symbol
- git_show_commit / get_commit_detail
- Git Agent Tools (git_last_change, git_history, git_blame_symbol, git_show_commit)
- Intent classification for Git queries
- Git API endpoints (/api/git/last-change, /api/git/history, /api/git/blame, /api/git/commit/{commit})
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agent.intent import QuestionIntent, classify_question_intent
from app.agent.tools import (
    create_git_blame_symbol_tool,
    create_git_history_tool,
    create_git_last_change_tool,
    create_git_show_commit_tool,
)
from app.git import (
    GitCommitNotFoundError,
    GitFileNotFoundError,
    get_blame_for_symbol,
    get_commit_detail,
    get_history_for_symbol,
    get_last_change_for_symbol,
    get_repository,
    resolve_symbol_location,
)


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


@pytest.fixture
def repo(project_root: Path):
    return get_repository(project_root)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Symbol Location Resolution Tests
# ==============================================================================

def test_resolve_symbol_location_file_path(project_root: Path):
    res = resolve_symbol_location("app/graph/builder.py", project_root=project_root)
    assert res is not None
    file_path, start_line, end_line = res
    assert "builder.py" in file_path
    assert start_line == 1
    assert end_line > 10


def test_resolve_symbol_location_method(project_root: Path):
    res = resolve_symbol_location("GraphBuilder.build", project_root=project_root)
    assert res is not None
    file_path, start_line, end_line = res
    assert "builder.py" in file_path
    assert start_line > 0


def test_resolve_symbol_location_class(project_root: Path):
    res = resolve_symbol_location("GraphBuilder", project_root=project_root)
    assert res is not None
    file_path, start_line, end_line = res
    assert "builder.py" in file_path
    assert start_line > 0


def test_resolve_symbol_location_nonexistent(project_root: Path):
    res = resolve_symbol_location("NonExistentSymbol_XYZ123", project_root=project_root)
    assert res is None


# ==============================================================================
# 2. Symbol Git Functions Tests
# ==============================================================================

def test_get_last_change_for_symbol(repo, project_root: Path):
    res = get_last_change_for_symbol(repo=repo, symbol="GraphBuilder.build", project_root=project_root)
    assert res.symbol == "GraphBuilder.build"
    assert res.file == "app/graph/builder.py"
    assert res.commit is not None
    assert len(res.short_hash) == 7
    assert res.author != ""
    assert res.date != ""


def test_get_last_change_for_file(repo, project_root: Path):
    res = get_last_change_for_symbol(repo=repo, symbol="app/main.py", project_root=project_root)
    assert res.symbol == "app/main.py"
    assert "main.py" in res.file
    assert res.commit is not None


def test_get_last_change_missing_symbol(repo, project_root: Path):
    with pytest.raises(GitFileNotFoundError):
        get_last_change_for_symbol(repo=repo, symbol="NonExistentSymbol9999", project_root=project_root)


def test_get_history_for_symbol(repo, project_root: Path):
    res = get_history_for_symbol(repo=repo, symbol="GraphBuilder.build", limit=5, project_root=project_root)
    assert res["symbol"] == "GraphBuilder.build"
    assert "builder.py" in res["file"]
    assert res["total_commits"] > 0
    assert len(res["commits"]) <= 5
    first_commit = res["commits"][0]
    assert "short_hash" in first_commit
    assert "author_name" in first_commit


def test_get_blame_for_symbol(repo, project_root: Path):
    res = get_blame_for_symbol(repo=repo, symbol="GraphBuilder.build", project_root=project_root)
    assert res["symbol"] == "GraphBuilder.build"
    assert "builder.py" in res["file"]
    assert res["total_lines"] > 0
    assert len(res["contributors"]) > 0
    assert res["primary_contributor"] in res["contributors"]
    assert len(res["lines"]) > 0


def test_get_commit_detail_valid(repo):
    detail = get_commit_detail(repo=repo, commit_hash="HEAD")
    assert detail.commit_hash is not None
    assert detail.short_hash is not None
    assert detail.author_name != ""
    assert isinstance(detail.files_changed, list)


def test_get_commit_detail_invalid(repo):
    with pytest.raises(GitCommitNotFoundError):
        get_commit_detail(repo=repo, commit_hash="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")


# ==============================================================================
# 3. Agent Git Tools Tests
# ==============================================================================

def test_git_last_change_tool(project_root: Path):
    tool_spec = create_git_last_change_tool(project_root=project_root)
    assert tool_spec["name"] == "git_last_change"
    res = tool_spec["func"](symbol="GraphBuilder.build")
    assert "data" in res
    assert res["data"]["symbol"] == "GraphBuilder.build"
    assert len(res["sources"]) > 0
    assert res["sources"][0]["source_type"] == "git"


def test_git_history_tool(project_root: Path):
    tool_spec = create_git_history_tool(project_root=project_root)
    assert tool_spec["name"] == "git_history"
    res = tool_spec["func"](symbol="GraphBuilder.build", limit=3)
    assert "data" in res
    assert res["data"]["symbol"] == "GraphBuilder.build"
    assert len(res["sources"]) > 0


def test_git_blame_symbol_tool(project_root: Path):
    tool_spec = create_git_blame_symbol_tool(project_root=project_root)
    assert tool_spec["name"] == "git_blame_symbol"
    res = tool_spec["func"](symbol="GraphBuilder.build")
    assert "data" in res
    assert res["data"]["symbol"] == "GraphBuilder.build"
    assert len(res["sources"]) > 0


def test_git_show_commit_tool(project_root: Path):
    tool_spec = create_git_show_commit_tool(project_root=project_root)
    assert tool_spec["name"] == "git_show_commit"
    res = tool_spec["func"](commit="HEAD")
    assert "data" in res
    assert "commit_hash" in res["data"]
    assert len(res["sources"]) > 0


# ==============================================================================
# 4. Intent Classification for Git Questions Tests
# ==============================================================================

def test_classify_intent_git_last_change():
    c = classify_question_intent("Who last changed GraphBuilder.build?")
    assert c.intent == QuestionIntent.GIT_LAST_CHANGE
    assert c.target_symbol == "GraphBuilder.build"
    assert "git_last_change" in c.preferred_tools

    c2 = classify_question_intent("When was GraphBuilder.build last modified?")
    assert c2.intent == QuestionIntent.GIT_LAST_CHANGE
    assert c2.target_symbol == "GraphBuilder.build"

    c3 = classify_question_intent("Who introduced the current implementation of GraphBuilder.build?")
    assert c3.intent == QuestionIntent.GIT_LAST_CHANGE
    assert c3.target_symbol == "GraphBuilder.build"


def test_classify_intent_git_history():
    c = classify_question_intent("Show me the history of GraphBuilder.build")
    assert c.intent == QuestionIntent.GIT_HISTORY
    assert c.target_symbol == "GraphBuilder.build"
    assert "git_history" in c.preferred_tools


def test_classify_intent_git_blame():
    c = classify_question_intent("Who wrote GraphBuilder.build?")
    assert c.intent == QuestionIntent.GIT_BLAME
    assert c.target_symbol == "GraphBuilder.build"
    assert "git_blame_symbol" in c.preferred_tools


def test_classify_intent_git_change_and_impact():
    c = classify_question_intent("What changed around GraphBuilder.build and what could be affected?")
    assert c.intent == QuestionIntent.GIT_CHANGE_AND_IMPACT
    assert c.target_symbol == "GraphBuilder.build"
    assert "git_last_change" in c.preferred_tools
    assert "get_impact" in c.preferred_tools


def test_classify_intent_git_show_commit():
    c = classify_question_intent("Show commit a0635cd")
    assert c.intent == QuestionIntent.GIT_SHOW_COMMIT
    assert c.target_symbol == "a0635cd"
    assert "git_show_commit" in c.preferred_tools

    c2 = classify_question_intent("Details of commit a0635cd")
    assert c2.intent == QuestionIntent.GIT_SHOW_COMMIT
    assert c2.target_symbol == "a0635cd"


# ==============================================================================
# 5. Git API Endpoints Tests
# ==============================================================================

def test_api_git_last_change_success(client: TestClient):
    response = client.get("/api/git/last-change", params={"symbol": "GraphBuilder.build"})
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["file"] == "app/graph/builder.py"
    assert len(data["short_hash"]) == 7
    assert data["author"] != ""


def test_api_git_last_change_missing_symbol(client: TestClient):
    response = client.get("/api/git/last-change", params={"symbol": "MissingSymbolXYZ999"})
    assert response.status_code == 404


def test_api_git_history_success(client: TestClient):
    response = client.get("/api/git/history", params={"symbol": "GraphBuilder.build", "limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["total_commits"] > 0
    assert len(data["commits"]) <= 5


def test_api_git_blame_success(client: TestClient):
    response = client.get("/api/git/blame", params={"symbol": "GraphBuilder.build"})
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "GraphBuilder.build"
    assert data["total_lines"] > 0
    assert data["primary_contributor"] != ""
    assert len(data["lines"]) > 0


def test_api_git_commit_detail_success(client: TestClient):
    response = client.get("/api/git/commit/HEAD")
    assert response.status_code == 200
    data = response.json()
    assert "commit_hash" in data
    assert "short_hash" in data
    assert "author_name" in data
    assert isinstance(data["files_changed"], list)


def test_api_git_commit_detail_not_found(client: TestClient):
    response = client.get("/api/git/commit/0000000000000000000000000000000000000000")
    assert response.status_code == 404
