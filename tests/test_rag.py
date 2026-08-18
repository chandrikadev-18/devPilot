"""
Tests for RAG Pipeline and Codebase Q&A.
"""

import json
import os
from unittest.mock import MagicMock
import pytest

from app.embeddings.embedder import CodeEmbedder, DEFAULT_EMBEDDING_MODEL
from app.indexer.chunker import CodeChunk
from app.llm.base import LLMProvider
from app.rag.context_builder import ContextBuilder
from app.rag.qa import (
    DEFAULT_SYSTEM_PROMPT,
    NO_RELEVANT_CONTEXT_ANSWER,
    QAResult,
    RAGPipeline,
)
from app.search.semantic_search import SearchResult, SemanticSearcher
from app.vector_store.qdrant_store import QdrantVectorStore


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for deterministic testing without external API calls."""

    def __init__(
        self,
        canned_response: str = "Authentication is handled in backend/auth.py.",
        provider_name: str = "groq",
        model_name: str = "mock-model",
    ):
        self._canned_response = canned_response
        self._provider_name = provider_name
        self._model_name = model_name
        self.call_count = 0
        self.last_prompt = None
        self.last_system_prompt = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return self._canned_response

    def chat(self, messages, tools=None):
        self.call_count += 1
        return LLMChatResponse(content=self._canned_response)


@pytest.fixture
def mock_searcher():
    """Mock SemanticSearcher returning predefined SearchResults."""
    searcher = MagicMock(spec=SemanticSearcher)
    searcher.search.return_value = [
        SearchResult(
            chunk_id="chunk-auth-1",
            score=0.8920,
            file_path="backend/auth.py",
            symbol_name="authenticate_user",
            symbol_type="function",
            parent_symbol=None,
            start_line=10,
            end_line=22,
            code="def authenticate_user(username, password):\n    return check_password(username, password)",
            metadata={"extension": ".py"},
        ),
        SearchResult(
            chunk_id="chunk-auth-svc",
            score=0.8350,
            file_path="backend/auth_service.py",
            symbol_name="login",
            symbol_type="method",
            parent_symbol="AuthService",
            start_line=30,
            end_line=42,
            code="def login(self, username, password):\n    return self.authenticate_user(username, password)",
            metadata={"extension": ".py"},
        ),
    ]
    return searcher


def test_rag_pipeline_ask_flow(mock_searcher):
    """Verifies that RAGPipeline executes search, builds context, and invokes LLM."""
    mock_llm = MockLLMProvider(
        canned_response="Authentication is primarily handled in backend/auth.py via authenticate_user()."
    )
    pipeline = RAGPipeline(searcher=mock_searcher, llm=mock_llm)

    result = pipeline.ask("Where is authentication handled?", top_k=5)

    # 1. Verify searcher called
    mock_searcher.search.assert_called_once_with(
        query="Where is authentication handled?",
        top_k=5,
        min_score=None,
        extension=None,
        path_prefix=None,
        symbol_type=None,
    )

    # 2. Verify LLM called
    assert mock_llm.call_count == 1
    assert "User Question:\nWhere is authentication handled?" in mock_llm.last_prompt
    assert "backend/auth.py" in mock_llm.last_prompt
    assert mock_llm.last_system_prompt == DEFAULT_SYSTEM_PROMPT

    # 3. Verify QAResult structure
    assert result.question == "Where is authentication handled?"
    assert result.answer == "Authentication is primarily handled in backend/auth.py via authenticate_user()."
    assert result.provider == "groq"
    assert result.model == "mock-model"
    assert len(result.sources) == 2
    assert result.sources[0]["file_path"] == "backend/auth.py"
    assert result.sources[0]["symbol_name"] == "authenticate_user"
    assert result.sources[0]["start_line"] == 10
    assert result.sources[0]["end_line"] == 22
    assert result.sources[0]["score"] == 0.8920

    # 4. Verify timings
    assert "search" in result.timings
    assert "llm" in result.timings
    assert "total" in result.timings
    assert result.timings["total"] >= 0.0


def test_rag_pipeline_empty_retrieval():
    """Verifies that empty search results do not call LLM and return informative message."""
    empty_searcher = MagicMock(spec=SemanticSearcher)
    empty_searcher.search.return_value = []

    mock_llm = MockLLMProvider()
    pipeline = RAGPipeline(searcher=empty_searcher, llm=mock_llm)

    result = pipeline.ask("Something unrelated to codebase")

    assert mock_llm.call_count == 0
    assert result.answer == NO_RELEVANT_CONTEXT_ANSWER
    assert result.sources == []
    assert result.search_results == []
    assert result.context_used == ""


def test_qa_result_json_serialization(mock_searcher):
    """Verifies that QAResult converts cleanly to JSON."""
    mock_llm = MockLLMProvider()
    pipeline = RAGPipeline(searcher=mock_searcher, llm=mock_llm)

    result = pipeline.ask("Where is user authentication handled?")
    as_dict = result.to_dict()

    json_str = json.dumps(as_dict, indent=2)
    parsed = json.loads(json_str)

    assert parsed["question"] == "Where is user authentication handled?"
    assert "answer" in parsed
    assert isinstance(parsed["sources"], list)
    assert len(parsed["sources"]) == 2
    assert parsed["provider"] == "groq"
    assert "timings" in parsed
    assert "search" in parsed["timings"]
    assert "llm" in parsed["timings"]


def test_rag_integration_end_to_end():
    """
    End-to-end integration test of the full DevPilot v0.7 pipeline:
    CodeChunks -> Embeddings -> In-memory Qdrant -> SemanticSearcher -> ContextBuilder -> MockLLM -> QAResult.
    """
    embedder = CodeEmbedder(model_name=DEFAULT_EMBEDDING_MODEL)
    store = QdrantVectorStore(location=":memory:")
    col_name = "test_rag_col"
    store.create_collection(collection_name=col_name, vector_size=embedder.dimension)

    chunks = [
        CodeChunk(
            id="chunk-auth-1",
            file_path="sample_project/auth.py",
            language="python",
            symbol_name="AuthService",
            symbol_type="class",
            parent_symbol=None,
            start_line=4,
            end_line=12,
            code="class AuthService:\n    def hash_password(self, password):\n        return hashlib.sha256(password.encode()).hexdigest()\n    def verify_password(self, password, hashed):\n        return self.hash_password(password) == hashed",
            metadata={"extension": ".py", "imports": ["hashlib", "os"]},
        ),
        CodeChunk(
            id="chunk-auth-2",
            file_path="sample_project/auth.py",
            language="python",
            symbol_name="login_user",
            symbol_type="function",
            parent_symbol=None,
            start_line=14,
            end_line=15,
            code="def login_user(username, password):\n    pass",
            metadata={"extension": ".py", "imports": ["hashlib", "os"]},
        ),
        CodeChunk(
            id="chunk-users-1",
            file_path="sample_project/users.py",
            language="python",
            symbol_name="get_user_by_id",
            symbol_type="function",
            parent_symbol=None,
            start_line=3,
            end_line=4,
            code="def get_user_by_id(user_id):\n    return {'id': user_id, 'username': 'test_user'}",
            metadata={"extension": ".py", "imports": ["auth"]},
        ),
    ]

    vectors = embedder.embed_chunks(chunks)
    store.upsert_chunks(chunks=chunks, vectors=vectors, collection_name=col_name)

    searcher = SemanticSearcher(
        embedder=embedder,
        vector_store=store,
        collection_name=col_name,
    )

    mock_llm = MockLLMProvider(
        canned_response=(
            "User authentication and password verification are handled in sample_project/auth.py "
            "within the AuthService class (lines 4-12)."
        )
    )

    pipeline = RAGPipeline(searcher=searcher, llm=mock_llm)

    result = pipeline.ask("Where is password hashing and authentication handled?", top_k=2)

    assert result.answer.startswith("User authentication and password verification are handled")
    assert len(result.sources) > 0
    assert result.sources[0]["file_path"] == "sample_project/auth.py"
    assert mock_llm.call_count == 1
    assert "sample_project/auth.py" in mock_llm.last_prompt


@pytest.mark.skipif(
    not os.getenv("RUN_LLM_INTEGRATION_TESTS"),
    reason="Live LLM tests require RUN_LLM_INTEGRATION_TESTS=1 and a valid LLM_API_KEY",
)
def test_real_groq_provider_live():
    """Opt-in live integration test against Groq API."""
    from app.llm.provider import GroqProvider

    provider = GroqProvider()
    response = provider.generate(
        prompt="Explain what a binary search tree is in one short sentence.",
        system_prompt="You are a concise computer science tutor.",
    )
    assert len(response) > 10
