"""
Tests for Context Builder.
"""

import pytest

from app.rag.context_builder import ContextBuilder, SourceCitation
from app.search.semantic_search import SearchResult


@pytest.fixture
def sample_search_results():
    """Provides sample SearchResult objects for context builder tests."""
    return [
        SearchResult(
            chunk_id="chunk-auth-1",
            score=0.8850,
            file_path="backend/auth.py",
            symbol_name="authenticate_user",
            symbol_type="function",
            parent_symbol=None,
            start_line=10,
            end_line=25,
            code="def authenticate_user(username, password):\n    return check_password(username, password)",
            metadata={"extension": ".py"},
        ),
        SearchResult(
            chunk_id="chunk-auth-svc",
            score=0.8240,
            file_path="backend/auth_service.py",
            symbol_name="login",
            symbol_type="method",
            parent_symbol="AuthService",
            start_line=30,
            end_line=45,
            code="def login(self, username, password):\n    return self.auth.authenticate_user(username, password)",
            metadata={"extension": ".py"},
        ),
        SearchResult(
            chunk_id="chunk-user-model",
            score=0.7510,
            file_path="models/user.py",
            symbol_name="User",
            symbol_type="class",
            parent_symbol=None,
            start_line=1,
            end_line=20,
            code="class User:\n    def __init__(self, id, username):\n        self.id = id\n        self.username = username",
            metadata={"extension": ".py"},
        ),
    ]


def test_build_context_structure(sample_search_results):
    """Verifies that SearchResult objects are formatted into expected structured context."""
    builder = ContextBuilder(max_chunks=5, max_characters=10000)
    context_str, citations = builder.build_context(sample_search_results)

    assert "--- SOURCE 1 ---" in context_str
    assert "File: backend/auth.py" in context_str
    assert "Symbol: authenticate_user" in context_str
    assert "Type: function" in context_str
    assert "Lines: 10-25" in context_str
    assert "Score: 0.8850" in context_str
    assert "def authenticate_user(username, password):" in context_str

    assert "--- SOURCE 2 ---" in context_str
    assert "File: backend/auth_service.py" in context_str
    assert "Symbol: login" in context_str
    assert "Type: method" in context_str
    assert "Class: AuthService" in context_str
    assert "Lines: 30-45" in context_str

    assert len(citations) == 3
    assert citations[0].chunk_id == "chunk-auth-1"
    assert citations[0].file_path == "backend/auth.py"
    assert citations[0].symbol_name == "authenticate_user"
    assert citations[0].start_line == 10
    assert citations[0].end_line == 25
    assert citations[0].score == 0.8850


def test_build_context_max_chunks_limit(sample_search_results):
    """Verifies max_chunks bounds the context to top most relevant items."""
    builder = ContextBuilder(max_chunks=2, max_characters=10000)
    context_str, citations = builder.build_context(sample_search_results)

    assert len(citations) == 2
    assert "--- SOURCE 1 ---" in context_str
    assert "--- SOURCE 2 ---" in context_str
    assert "--- SOURCE 3 ---" not in context_str
    assert citations[0].chunk_id == "chunk-auth-1"
    assert citations[1].chunk_id == "chunk-auth-svc"


def test_build_context_max_characters_limit(sample_search_results):
    """Verifies context is safely truncated when exceeding character limits."""
    # Small character budget
    builder = ContextBuilder(max_chunks=5, max_characters=400)
    context_str, citations = builder.build_context(sample_search_results)

    assert len(context_str) <= 500
    assert "--- SOURCE 1 ---" in context_str
    # Either truncated notice is present or fewer chunks included
    assert len(citations) <= 2


def test_build_context_empty_results():
    """Verifies building context with empty search results returns empty string and empty citations."""
    builder = ContextBuilder()
    context_str, citations = builder.build_context([])

    assert context_str == ""
    assert citations == []


def test_source_citation_to_dict():
    """Verifies SourceCitation serialization to dictionary."""
    citation = SourceCitation(
        chunk_id="chunk-123",
        file_path="app/main.py",
        symbol_name="run_scan",
        symbol_type="function",
        parent_symbol=None,
        start_line=30,
        end_line=45,
        score=0.912345,
    )
    d = citation.to_dict()
    assert d == {
        "chunk_id": "chunk-123",
        "file_path": "app/main.py",
        "symbol_name": "run_scan",
        "symbol_type": "function",
        "start_line": 30,
        "end_line": 45,
        "score": 0.9123,
    }
