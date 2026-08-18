"""
Tests for Read-Only Codebase Tools and Security Guardrails.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.agent.tools import (
    SecurityError,
    create_find_symbol_tool,
    create_get_file_structure_tool,
    create_read_file_tool,
    create_search_code_tool,
    resolve_safe_path,
)
from app.search.semantic_search import SearchResult, SemanticSearcher


@pytest.fixture
def temp_project(tmp_path):
    """Creates a temporary project directory with sample files for security testing."""
    proj = tmp_path / "my_project"
    proj.mkdir()

    # Sample Python files
    (proj / "auth.py").write_text(
        "class AuthService:\n    def login(self):\n        pass\n\ndef check_auth():\n    return True\n",
        encoding="utf-8",
    )
    (proj / "utils.py").write_text("def helper():\n    return 42\n", encoding="utf-8")

    # Sensitive files
    (proj / ".env").write_text("SECRET_KEY=supersecret123\n", encoding="utf-8")
    (proj / ".env.local").write_text("API_KEY=testkey\n", encoding="utf-8")

    git_dir = proj / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")

    # Outside secret file
    (tmp_path / "outside_secret.txt").write_text("CONFIDENTIAL", encoding="utf-8")

    return proj


def test_resolve_safe_path_valid(temp_project):
    """Verifies that valid project files resolve correctly."""
    resolved = resolve_safe_path("auth.py", project_root=temp_project)
    assert resolved == (temp_project / "auth.py").resolve()


def test_resolve_safe_path_traversal_rejection(temp_project):
    """Verifies that directory traversal attempts are rejected."""
    with pytest.raises(SecurityError) as exc:
        resolve_safe_path("../outside_secret.txt", project_root=temp_project)
    assert "Directory traversal is forbidden" in str(exc.value)


def test_resolve_safe_path_env_rejection(temp_project):
    """Verifies that .env files cannot be accessed."""
    with pytest.raises(SecurityError) as exc:
        resolve_safe_path(".env", project_root=temp_project)
    assert "Access to environment files is forbidden" in str(exc.value)

    with pytest.raises(SecurityError) as exc:
        resolve_safe_path(".env.local", project_root=temp_project)
    assert "Access to environment files is forbidden" in str(exc.value)


def test_resolve_safe_path_git_rejection(temp_project):
    """Verifies that .git files cannot be accessed."""
    with pytest.raises(SecurityError) as exc:
        resolve_safe_path(".git/config", project_root=temp_project)
    assert "Access to internal .git directory is forbidden" in str(exc.value)


def test_resolve_safe_path_outside_project_absolute(temp_project, tmp_path):
    """Verifies that absolute paths outside project root are rejected."""
    outside_file = str(tmp_path / "outside_secret.txt")
    with pytest.raises(SecurityError) as exc:
        resolve_safe_path(outside_file, project_root=temp_project)
    assert "resolves outside project root" in str(exc.value)


def test_read_file_tool(temp_project):
    """Verifies read_file returns content and source metadata."""
    tool_spec = create_read_file_tool(project_root=temp_project)
    func = tool_spec["func"]

    result = func(file_path="auth.py")
    assert "class AuthService:" in result["data"]["content"]
    assert result["data"]["lines"] == len(result["data"]["content"].splitlines())
    assert len(result["sources"]) == 1
    assert result["sources"][0]["file_path"] == "auth.py"


def test_read_file_truncation(temp_project):
    """Verifies read_file truncates files exceeding max_characters."""
    tool_spec = create_read_file_tool(project_root=temp_project, max_characters=30)
    func = tool_spec["func"]

    result = func(file_path="auth.py")
    assert result["data"]["truncated"] is True
    assert "[File truncated due to size limit]" in result["data"]["content"]


def test_read_file_non_existent(temp_project):
    """Verifies read_file raises FileNotFoundError for missing files."""
    tool_spec = create_read_file_tool(project_root=temp_project)
    func = tool_spec["func"]

    with pytest.raises(FileNotFoundError):
        func(file_path="non_existent.py")


def test_search_code_tool():
    """Verifies search_code delegates to SemanticSearcher and formats results."""
    mock_searcher = MagicMock(spec=SemanticSearcher)
    mock_searcher.search.return_value = [
        SearchResult(
            chunk_id="chunk-1",
            score=0.88,
            file_path="auth.py",
            symbol_name="login",
            symbol_type="method",
            parent_symbol="AuthService",
            start_line=2,
            end_line=3,
            code="def login(self):\n    pass",
        )
    ]

    tool_spec = create_search_code_tool(searcher=mock_searcher)
    func = tool_spec["func"]

    result = func(query="user login", top_k=3)
    mock_searcher.search.assert_called_once_with(query="user login", top_k=3)
    assert len(result["data"]) == 1
    assert result["data"][0]["symbol_name"] == "login"
    assert len(result["sources"]) == 1


def test_find_symbol_tool(temp_project):
    """Verifies find_symbol locates classes, functions, and methods."""
    tool_spec = create_find_symbol_tool(project_root=temp_project)
    func = tool_spec["func"]

    res_class = func(symbol_name="AuthService")
    assert len(res_class["data"]) >= 1
    assert res_class["data"][0]["symbol_name"] == "AuthService"
    assert res_class["data"][0]["symbol_type"] == "class"

    res_fn = func(symbol_name="check_auth")
    assert len(res_fn["data"]) >= 1
    assert res_fn["data"][0]["symbol_name"] == "check_auth"


def test_get_file_structure_tool(temp_project):
    """Verifies get_file_structure extracts AST metadata without executing code."""
    tool_spec = create_get_file_structure_tool(project_root=temp_project)
    func = tool_spec["func"]

    res = func(file_path="auth.py")
    data = res["data"]
    assert "classes" in data
    assert len(data["classes"]) == 1
    assert data["classes"][0]["name"] == "AuthService"
    assert len(data["functions"]) == 1
    assert data["functions"][0]["name"] == "check_auth"
    assert len(data["methods"]) == 1
    assert data["methods"][0]["name"] == "login"
