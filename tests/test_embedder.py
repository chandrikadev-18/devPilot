import json
import pytest
from pathlib import Path
from app.indexer.chunker import CodeChunk
from app.embeddings.embedder import (
    CodeEmbedder,
    build_embedding_text,
    save_embedding_index,
    load_embedding_index,
    DEFAULT_EMBEDDING_MODEL,
)


@pytest.fixture(scope="module")
def embedder():
    """Module-scoped embedder fixture so the model is loaded only once across tests."""
    return CodeEmbedder(model_name=DEFAULT_EMBEDDING_MODEL)


@pytest.fixture
def sample_function_chunk():
    return CodeChunk(
        id="chunk-fn-1",
        file_path="backend/auth.py",
        language="python",
        symbol_name="authenticate_user",
        symbol_type="function",
        parent_symbol=None,
        start_line=10,
        end_line=20,
        code="def authenticate_user(username, password):\n    return username == 'admin'",
        metadata={"extension": ".py", "imports": ["import os"]},
    )


@pytest.fixture
def sample_method_chunk():
    return CodeChunk(
        id="chunk-m-1",
        file_path="backend/users.py",
        language="python",
        symbol_name="save",
        symbol_type="method",
        parent_symbol="User",
        start_line=15,
        end_line=18,
        code="def save(self):\n    db.session.add(self)",
        metadata={"extension": ".py", "imports": ["from db import session"]},
    )


def test_build_embedding_text_function(sample_function_chunk):
    """Verify semantic text representation for a function CodeChunk."""
    text = build_embedding_text(sample_function_chunk)
    assert "File: backend/auth.py" in text
    assert "Language: python" in text
    assert "Type: function" in text
    assert "Symbol: authenticate_user" in text
    assert "Class:" not in text
    assert "def authenticate_user(username, password):" in text


def test_build_embedding_text_method(sample_method_chunk):
    """Verify semantic text representation for a method CodeChunk includes parent class."""
    text = build_embedding_text(sample_method_chunk)
    assert "File: backend/users.py" in text
    assert "Language: python" in text
    assert "Type: method" in text
    assert "Class: User" in text
    assert "Symbol: save" in text
    assert "def save(self):" in text


def test_model_initialization(embedder):
    """Verify the embedding model initializes and reports correct dimension."""
    assert embedder.model_name == DEFAULT_EMBEDDING_MODEL
    assert embedder.dimension > 0
    # BAAI/bge-small-en-v1.5 has 384 dimensions
    assert embedder.dimension == 384


def test_embed_single_text(embedder):
    """Verify single text embedding produces a vector of correct dimension."""
    text = "def authenticate_user(username, password): pass"
    vector = embedder.embed_text(text)

    assert isinstance(vector, list)
    assert len(vector) == embedder.dimension
    assert all(isinstance(val, float) for val in vector)


def test_vector_dimension_matches_model(embedder):
    """Verify vector length matches embedder.dimension dynamically."""
    vector = embedder.embed_text("sample code query")
    assert len(vector) == embedder.dimension


def test_batch_embedding_chunks(embedder, sample_function_chunk, sample_method_chunk):
    """Verify batch embedding returns matching number of vectors."""
    chunks = [sample_function_chunk, sample_method_chunk]
    vectors = embedder.embed_chunks(chunks, batch_size=2)

    assert len(vectors) == 2
    assert len(vectors[0]) == embedder.dimension
    assert len(vectors[1]) == embedder.dimension


def test_empty_input(embedder):
    """Verify empty input handling."""
    # Empty chunk list returns empty list
    assert embedder.embed_chunks([]) == []
    assert embedder.embed_texts([]) == []

    # Empty text raises ValueError
    with pytest.raises(ValueError):
        embedder.embed_text("")

    with pytest.raises(ValueError):
        embedder.embed_text("   ")


def test_deterministic_embedding(embedder):
    """Verify that same text produces identical normalized embeddings."""
    text = "class AuthService: pass"
    vec1 = embedder.embed_text(text)
    vec2 = embedder.embed_text(text)

    assert len(vec1) == len(vec2)
    for v1, v2 in zip(vec1, vec2):
        assert v1 == pytest.approx(v2, abs=1e-6)


def test_local_index_save_and_load(tmp_path, sample_function_chunk, sample_method_chunk):
    """Verify local development index serialization and deserialization."""
    index_file = tmp_path / "embeddings" / "index.json"
    chunks = [sample_function_chunk, sample_method_chunk]
    embeddings = [
        [0.1] * 384,
        [0.2] * 384,
    ]

    saved_path = save_embedding_index(
        output_path=index_file,
        model_name="BAAI/bge-small-en-v1.5",
        dimension=384,
        chunks=chunks,
        embeddings=embeddings,
    )

    assert saved_path.exists()

    loaded = load_embedding_index(saved_path)
    assert loaded["model"] == "BAAI/bge-small-en-v1.5"
    assert loaded["dimension"] == 384
    assert loaded["total_chunks"] == 2
    assert len(loaded["items"]) == 2

    first_item = loaded["items"][0]
    assert first_item["chunk_id"] == "chunk-fn-1"
    assert first_item["file_path"] == "backend/auth.py"
    assert first_item["symbol_name"] == "authenticate_user"
    assert first_item["symbol_type"] == "function"
    assert first_item["parent_symbol"] is None
    assert len(first_item["embedding"]) == 384
