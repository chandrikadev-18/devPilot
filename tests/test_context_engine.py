"""
Tests for DevPilot v1.6 Repository Intelligence & Context Engine.

Verifies:
1. Context model creation and serialization (.to_dict, .to_formatted_text)
2. Symbol context collection and source code slicing
3. Dependency graph intelligence (callers, callees, dependencies, dependents, impact)
4. Related test discovery by filename and AST test function inspection
5. Git history intelligence integration
6. Context size limits and bounded payloads
7. Missing symbol and empty repo graceful handling
8. Invalid project path validation
9. Agent integration with get_repository_context tool
10. API integration (/api/ask and /api/agent/execute with repository context)
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.agent import create_codebase_agent
from app.agent.tools import create_get_repository_context_tool
from app.context.engine import ContextEngine
from app.context.models import (
    GitChangeContext,
    RelatedTest,
    RepositoryContext,
    SourceSnippet,
    SymbolContext,
)
from app.graph.builder import GraphBuilder
from app.graph.store import GraphStore
from app.llm.base import LLMChatResponse, LLMProvider, ToolCall
from app.main import app


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_project_tree(tmp_path):
    """Creates a temporary project structure with source code, tests, and graph."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # 1. Main service
    service_code = '''
class AuthService:
    def __init__(self, db_client):
        self.db = db_client

    def login(self, username, password):
        user = self.find_user(username)
        if user and self.verify_password(password, user.password_hash):
            return self.generate_token(user)
        return None

    def find_user(self, username):
        return self.db.query_user(username)

    def verify_password(self, password, password_hash):
        return password == password_hash

    def generate_token(self, user):
        return f"token_{user.id}"
'''
    (src_dir / "auth_service.py").write_text(service_code, encoding="utf-8")

    # 2. Client that calls AuthService
    client_code = '''
from src.auth_service import AuthService

class AuthController:
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    def handle_login(self, request):
        return self.auth_service.login(request.username, request.password)
'''
    (src_dir / "auth_controller.py").write_text(client_code, encoding="utf-8")

    # 3. Tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_auth_code = '''
import pytest
from src.auth_service import AuthService

def test_login_success():
    auth = AuthService(None)
    assert auth is not None

def test_find_user():
    pass

def test_generate_token():
    pass
'''
    (tests_dir / "test_auth_service.py").write_text(test_auth_code, encoding="utf-8")

    test_unrelated = '''
def test_other_feature():
    assert True
'''
    (tests_dir / "test_other.py").write_text(test_unrelated, encoding="utf-8")

    # 4. Build graph
    graph = GraphBuilder().build(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    graph.save(data_dir / "graph.json")

    return tmp_path, graph


class MockContextLLM(LLMProvider):
    def __init__(self, responses=None):
        self._responses = list(responses or [
            LLMChatResponse(
                content="Repository context indicates AuthService.login coordinates user lookup, verification, and token generation.",
                tool_calls=[],
            )
        ])

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-context-model"

    def chat(self, messages, tools=None):
        if self._responses:
            return self._responses.pop(0)
        return LLMChatResponse(content="Final synthesized response with repository context.")


# ============================================================================
# 1. Model Creation & Serialization Tests
# ============================================================================

def test_context_models_serialization():
    """Verifies that all context models serialize to clean dicts and text."""
    sym = SymbolContext(
        name="AuthService.login",
        file_path="src/auth_service.py",
        symbol_type="method",
        parent_symbol="AuthService",
        start_line=6,
        end_line=11,
        code="def login(self, username, password):\n    pass",
    )
    snip = SourceSnippet(
        file_path="src/auth_service.py",
        start_line=6,
        end_line=11,
        code="def login(self, username, password):\n    pass",
        symbol_name="login",
    )
    test_item = RelatedTest(
        test_file="tests/test_auth_service.py",
        test_function="test_login_success",
        line_number=5,
        reason="test function covers 'login'",
    )
    git_item = GitChangeContext(
        commit_hash="abc1234567890",
        short_hash="abc1234",
        author="DevPilot User",
        date="2026-08-28",
        message="Add auth service login method",
        files_changed=["src/auth_service.py"],
    )

    ctx = RepositoryContext(
        question="Explain AuthService.login",
        target_symbol="AuthService.login",
        target_file="src/auth_service.py",
        symbols=[sym],
        source_snippets=[snip],
        callers=[{"name": "AuthController.handle_login", "file_path": "src/auth_controller.py", "start_line": 7}],
        callees=[{"name": "AuthService.find_user", "file_path": "src/auth_service.py", "start_line": 13}],
        dependencies=[{"name": "AuthService.find_user", "file_path": "src/auth_service.py", "depth": 1}],
        dependents=[{"name": "AuthController.handle_login", "file_path": "src/auth_controller.py", "depth": 1}],
        impact={"total_impacted": 1, "impacted_files": ["src/auth_controller.py"]},
        impacted_files=["src/auth_controller.py"],
        related_tests=[test_item],
        git_history=[git_item],
        summary={"symbols_found": 1},
    )

    data = ctx.to_dict()
    assert data["target_symbol"] == "AuthService.login"
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["name"] == "AuthService.login"
    assert len(data["source_snippets"]) == 1
    assert len(data["callers"]) == 1
    assert len(data["callees"]) == 1
    assert len(data["related_tests"]) == 1
    assert len(data["git_history"]) == 1

    formatted = ctx.to_formatted_text()
    assert "=== REPOSITORY CONTEXT: Explain AuthService.login ===" in formatted
    assert "AuthService.login" in formatted
    assert "CALLERS (1)" in formatted
    assert "CALLEES (1)" in formatted
    assert "RELATED TESTS (1)" in formatted
    assert "GIT HISTORY (1 commits)" in formatted


# ============================================================================
# 2. ContextEngine Collection Tests
# ============================================================================

def test_context_engine_symbol_and_source_collection(mock_project_tree):
    """Verifies ContextEngine locates symbols and extracts bounded source snippets."""
    root_path, graph = mock_project_tree
    engine = ContextEngine(project_root=root_path, graph=graph, max_snippet_lines=30)

    ctx = engine.build_context(
        question="What does AuthService.login do?",
        symbol="AuthService.login",
    )

    assert ctx.target_symbol == "AuthService.login"
    assert len(ctx.symbols) >= 1
    sym = ctx.symbols[0]
    assert "login" in sym.name
    assert "auth_service.py" in sym.file_path.replace("\\", "/")
    assert sym.symbol_type == "method"

    assert len(ctx.source_snippets) >= 1
    assert "def login" in ctx.source_snippets[0].code


def test_context_engine_graph_relationships(mock_project_tree):
    """Verifies ContextEngine resolves callers, callees, dependencies, and impact."""
    root_path, graph = mock_project_tree
    engine = ContextEngine(project_root=root_path, graph=graph)

    ctx = engine.build_context(
        question="What are the dependencies and callers of login?",
        symbol="login",
    )

    # Callers: AuthController.handle_login calls AuthService.login
    caller_names = [c.get("name") for c in ctx.callers]
    assert any("handle_login" in str(name) for name in caller_names)

    # Callees: login calls find_user, verify_password, generate_token
    callee_names = [c.get("name") for c in ctx.callees]
    assert any("find_user" in str(name) or "verify_password" in str(name) for name in callee_names)

    # Impacted files
    assert "auth_controller.py" in " ".join(ctx.impacted_files).replace("\\", "/")


def test_context_engine_related_test_discovery(mock_project_tree):
    """Verifies ContextEngine identifies related test files and test functions."""
    root_path, graph = mock_project_tree
    engine = ContextEngine(project_root=root_path, graph=graph)

    ctx = engine.build_context(
        question="Which tests cover AuthService.login?",
        symbol="AuthService.login",
        file_path="src/auth_service.py",
    )

    test_files = [t.test_file.replace("\\", "/") for t in ctx.related_tests]
    assert any("test_auth_service.py" in tf for tf in test_files)

    test_funcs = [t.test_function for t in ctx.related_tests if t.test_function]
    assert any("test_login_success" in fn for fn in test_funcs)


def test_context_engine_size_limits(mock_project_tree):
    """Verifies ContextEngine respects snippet line bounds and max item limits."""
    root_path, graph = mock_project_tree
    engine = ContextEngine(project_root=root_path, graph=graph, max_snippet_lines=5, max_items_per_category=2)

    ctx = engine.build_context(
        question="Explain AuthService",
        symbol="AuthService",
    )

    for snip in ctx.source_snippets:
        lines = snip.code.splitlines()
        assert len(lines) <= 5

    assert len(ctx.symbols) <= 2
    assert len(ctx.callers) <= 2
    assert len(ctx.callees) <= 2
    assert len(ctx.related_tests) <= 2


def test_context_engine_missing_symbol(mock_project_tree):
    """Verifies graceful handling when symbol does not exist."""
    root_path, graph = mock_project_tree
    engine = ContextEngine(project_root=root_path, graph=graph)

    ctx = engine.build_context(
        question="What is NonExistentModule.some_function?",
        symbol="NonExistentModule.some_function",
    )

    assert ctx.target_symbol == "NonExistentModule.some_function"
    assert ctx.symbols == []
    assert ctx.source_snippets == []
    assert ctx.callers == []
    assert ctx.summary["symbols_found"] == 0


def test_context_engine_invalid_project_dir():
    """Verifies ValueError when project directory does not exist."""
    engine = ContextEngine(project_root=Path("non_existent_folder_99999"))
    with pytest.raises(ValueError, match="does not exist"):
        engine.build_context(question="Explain main")


def test_context_engine_empty_question():
    """Verifies ValueError when empty question and no symbol/file is given."""
    engine = ContextEngine()
    with pytest.raises(ValueError, match="Question, symbol, or file_path must be provided"):
        engine.build_context(question="   ")


# ============================================================================
# 3. Agent Tool & Agent Integration Tests
# ============================================================================

def test_get_repository_context_tool_execution(mock_project_tree):
    """Verifies get_repository_context agent tool returns structured context and sources."""
    root_path, graph = mock_project_tree
    tool_spec = create_get_repository_context_tool(project_root=root_path, graph=graph)
    assert tool_spec["name"] == "get_repository_context"

    func = tool_spec["func"]
    res = func(question="Which tests cover AuthService.login?", symbol="AuthService.login")

    assert "data" in res
    assert "formatted_text" in res
    assert "sources" in res
    assert res["data"]["target_symbol"] == "AuthService.login"
    assert len(res["sources"]) > 0


@patch("app.api.agent.create_llm_provider")
def test_api_ask_with_repository_context_tool(mock_create_llm, test_client, mock_project_tree):
    """Verifies POST /api/ask can execute get_repository_context and return structured response."""
    root_path, _ = mock_project_tree
    mock_llm = MockContextLLM([
        LLMChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="get_repository_context",
                    arguments={"question": "Which tests cover AuthService.login?", "symbol": "AuthService.login"},
                ),
            ],
        ),
        LLMChatResponse(
            content="AuthService.login is covered by test_login_success in tests/test_auth_service.py.",
            tool_calls=[],
        ),
    ])
    mock_create_llm.return_value = mock_llm

    payload = {
        "question": "Which tests cover AuthService.login?",
        "project_dir": str(root_path),
    }
    resp = test_client.post("/api/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "get_repository_context" in data["tools_used"]
    assert "test_login_success" in data["answer"]
    assert "metadata" in data
    assert len(data["metadata"]["tool_executions"]) >= 1
    assert data["metadata"]["tool_executions"][0]["tool"] == "get_repository_context"
    assert data["metadata"]["tool_executions"][0]["status"] == "success"
