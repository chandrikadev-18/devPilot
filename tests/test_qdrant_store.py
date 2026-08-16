import os
import shutil
import pytest
from pathlib import Path
from qdrant_client.models import Distance

from app.indexer.chunker import CodeChunk, CodeChunker
from app.embeddings.embedder import CodeEmbedder, DEFAULT_EMBEDDING_MODEL
from app.scanner.scanner import ProjectScanner
from app.parser.python_parser import PythonParser
from app.vector_store.qdrant_store import (
    QdrantVectorStore,
    VectorStoreError,
    ConfigurationMismatchError,
    ValidationError,
    chunk_id_to_point_id,
    build_chunk_payload,
    DEFAULT_COLLECTION_NAME,
)


@pytest.fixture
def memory_store():
    """Provides an in-memory QdrantVectorStore instance for fast, isolated tests."""
    store = QdrantVectorStore(location=":memory:")
    yield store
    store.close()


@pytest.fixture
def sample_function_chunk():
    return CodeChunk(
        id="chunk-auth-1",
        file_path="backend/auth.py",
        language="python",
        symbol_name="authenticate_user",
        symbol_type="function",
        parent_symbol=None,
        start_line=10,
        end_line=20,
        code="def authenticate_user(username, password):\n    return username == 'admin'",
        metadata={"extension": ".py", "imports": ["os", "hashlib"]},
    )


@pytest.fixture
def sample_method_chunk():
    return CodeChunk(
        id="chunk-user-save-1",
        file_path="backend/models.py",
        language="python",
        symbol_name="save",
        symbol_type="method",
        parent_symbol="User",
        start_line=25,
        end_line=30,
        code="def save(self):\n    db.session.add(self)",
        metadata={"extension": ".py", "imports": ["from db import session"]},
    )


def test_qdrant_store_initialization(tmp_path):
    """Test store initialization in memory and on disk."""
    mem_store = QdrantVectorStore(location=":memory:")
    assert mem_store.client is not None
    mem_store.close()

    disk_path = tmp_path / "qdrant_test_data"
    disk_store = QdrantVectorStore(storage_path=str(disk_path))
    assert disk_store.client is not None
    assert disk_path.exists()
    disk_store.close()


def test_collection_creation_and_existence(memory_store):
    """Test creating a collection and verifying existence."""
    col_name = "test_col"
    assert not memory_store.collection_exists(col_name)

    created = memory_store.create_collection(
        collection_name=col_name,
        vector_size=384,
        distance=Distance.COSINE,
    )
    assert created is True
    assert memory_store.collection_exists(col_name)

    # Calling create again on existing collection with matching params returns False
    created_again = memory_store.create_collection(
        collection_name=col_name,
        vector_size=384,
        distance=Distance.COSINE,
        recreate=False,
    )
    assert created_again is False


def test_collection_info(memory_store):
    """Test retrieving collection metadata and stats."""
    col_name = "info_col"
    memory_store.create_collection(
        collection_name=col_name,
        vector_size=128,
        distance=Distance.COSINE,
    )

    info = memory_store.get_collection_info(col_name)
    assert info["collection_name"] == col_name
    assert info["vector_size"] == 128
    assert "cosine" in info["distance"].lower()
    assert info["points"] == 0
    assert info["status"] == "Ready"


def test_single_vector_insertion_and_retrieval(memory_store, sample_function_chunk):
    """Test single vector upsert and retrieval."""
    col_name = "single_test"
    memory_store.create_collection(col_name, vector_size=4)

    dummy_vector = [0.1, 0.2, 0.3, 0.4]
    count = memory_store.upsert_chunks(
        chunks=[sample_function_chunk],
        vectors=[dummy_vector],
        collection_name=col_name,
    )
    assert count == 1

    info = memory_store.get_collection_info(col_name)
    assert info["points"] == 1

    payload = memory_store.get_by_id(sample_function_chunk.id, collection_name=col_name)
    assert payload is not None
    assert payload["chunk_id"] == sample_function_chunk.id
    assert payload["symbol_name"] == "authenticate_user"
    assert payload["file_path"] == "backend/auth.py"
    assert payload["symbol_type"] == "function"
    assert payload["start_line"] == 10
    assert payload["end_line"] == 20


def test_batch_vector_insertion_and_payload_storage(
    memory_store, sample_function_chunk, sample_method_chunk
):
    """Test batch vector insertion and payload correctness."""
    col_name = "batch_test"
    chunks = [sample_function_chunk, sample_method_chunk]
    vectors = [
        [0.1, 0.2, 0.3, 0.4],
        [0.5, 0.6, 0.7, 0.8],
    ]

    count = memory_store.upsert_chunks(
        chunks=chunks,
        vectors=vectors,
        collection_name=col_name,
        batch_size=1,
    )
    assert count == 2

    info = memory_store.get_collection_info(col_name)
    assert info["points"] == 2

    # Verify first payload
    p1 = memory_store.get_by_id(sample_function_chunk.id, collection_name=col_name)
    assert p1["chunk_id"] == "chunk-auth-1"
    assert p1["parent_symbol"] is None
    assert "os" in p1["metadata"]["imports"]

    # Verify second payload
    p2 = memory_store.get_by_id(sample_method_chunk.id, collection_name=col_name)
    assert p2["chunk_id"] == "chunk-user-save-1"
    assert p2["parent_symbol"] == "User"
    assert p2["symbol_type"] == "method"


def test_deterministic_id_behavior():
    """Verify deterministic UUID mapping for chunk IDs."""
    chunk_id = "test-chunk-abc123"
    uuid1 = chunk_id_to_point_id(chunk_id)
    uuid2 = chunk_id_to_point_id(chunk_id)
    assert uuid1 == uuid2

    diff_uuid = chunk_id_to_point_id("different-chunk-xyz")
    assert uuid1 != diff_uuid


def test_reindexing_does_not_create_duplicates(memory_store, sample_function_chunk):
    """Verify that re-upserting the same chunk updates existing point without duplicate points."""
    col_name = "reindex_test"
    vec1 = [0.1, 0.2, 0.3, 0.4]
    vec2 = [0.9, 0.8, 0.7, 0.6]

    # First indexing
    memory_store.upsert_chunks([sample_function_chunk], [vec1], collection_name=col_name)
    info1 = memory_store.get_collection_info(col_name)
    assert info1["points"] == 1

    # Re-indexing the same chunk ID
    memory_store.upsert_chunks([sample_function_chunk], [vec2], collection_name=col_name)
    info2 = memory_store.get_collection_info(col_name)
    assert info2["points"] == 1

    # Verify payload is still intact
    payload = memory_store.get_by_id(sample_function_chunk.id, collection_name=col_name)
    assert payload["chunk_id"] == sample_function_chunk.id


def test_vector_dimension_validation(memory_store, sample_function_chunk):
    """Verify validation when vector dimension does not match collection dimension."""
    col_name = "dim_test"
    memory_store.create_collection(col_name, vector_size=4)

    # 3 dimensions instead of 4
    bad_vector = [0.1, 0.2, 0.3]
    with pytest.raises(ValidationError):
        memory_store.upsert_chunks([sample_function_chunk], [bad_vector], collection_name=col_name)


def test_configuration_mismatch_on_create(memory_store):
    """Verify error raised when opening existing collection with mismatched dimension."""
    col_name = "mismatch_col"
    memory_store.create_collection(col_name, vector_size=384)

    # Attempt to initialize with dimension 768
    with pytest.raises(ConfigurationMismatchError) as exc_info:
        memory_store.create_collection(col_name, vector_size=768, recreate=False)
    assert "Embedding configuration mismatch" in str(exc_info.value)


def test_mismatched_chunk_and_vector_count(memory_store, sample_function_chunk, sample_method_chunk):
    """Verify error raised when chunk list and vector list have different lengths."""
    col_name = "count_test"
    chunks = [sample_function_chunk, sample_method_chunk]
    vectors = [[0.1, 0.2, 0.3, 0.4]]  # 1 vector for 2 chunks

    with pytest.raises(ValidationError) as exc_info:
        memory_store.upsert_chunks(chunks, vectors, collection_name=col_name)
    assert "Mismatch between number of chunks" in str(exc_info.value)


def test_empty_and_malformed_vector_handling(memory_store, sample_function_chunk):
    """Verify handling of empty inputs and non-numeric vectors."""
    col_name = "empty_test"
    memory_store.create_collection(col_name, vector_size=4)

    # Empty chunk list
    assert memory_store.upsert_chunks([], [], collection_name=col_name) == 0

    # Non-numeric vector
    with pytest.raises(ValidationError):
        memory_store.upsert_chunks([sample_function_chunk], [["a", "b", "c", "d"]], collection_name=col_name)

    # Empty vector
    with pytest.raises(ValidationError):
        memory_store.upsert_chunks([sample_function_chunk], [[]], collection_name=col_name)


def test_collection_deletion_and_reset(memory_store, sample_function_chunk):
    """Test deleting and resetting a collection."""
    col_name = "delete_test"
    memory_store.create_collection(col_name, vector_size=4)
    memory_store.upsert_chunks([sample_function_chunk], [[0.1, 0.2, 0.3, 0.4]], collection_name=col_name)
    assert memory_store.collection_exists(col_name)

    deleted = memory_store.delete_collection(col_name)
    assert deleted is True
    assert not memory_store.collection_exists(col_name)

    # Deleting non-existent collection returns False
    assert memory_store.delete_collection(col_name) is False


def test_full_pipeline_integration(tmp_path):
    """
    End-to-end integration test:
    sample_project -> scanner -> parser -> chunker -> embedder -> Qdrant -> verify stored points.
    """
    sample_dir = Path("sample_project")
    if not sample_dir.exists():
        pytest.skip("sample_project directory not found")

    # 1. Scan
    scanner = ProjectScanner()
    files, stats = scanner.scan(str(sample_dir))
    python_files = [f for f in files if f.extension == ".py"]
    assert len(python_files) > 0

    # 2. Parse & Chunk
    parser = PythonParser()
    chunker = CodeChunker()
    chunks = []
    for f in python_files:
        parsed_res = parser.parse_file(f.absolute_path)
        if "error" not in parsed_res:
            file_chunks = chunker.chunk_parsed_file(parsed_res, file_path_override=f.relative_path)
            chunks.extend(file_chunks)

    assert len(chunks) > 0

    # 3. Embed
    embedder = CodeEmbedder(model_name=DEFAULT_EMBEDDING_MODEL)
    vectors = embedder.embed_chunks(chunks)
    assert len(vectors) == len(chunks)
    assert len(vectors[0]) == embedder.dimension

    # 4. Qdrant Store (in isolated temp directory)
    qdrant_dir = tmp_path / "test_pipeline_qdrant"
    store = QdrantVectorStore(storage_path=str(qdrant_dir))
    col_name = "test_pipeline"

    store.create_collection(collection_name=col_name, vector_size=embedder.dimension)
    stored_count = store.upsert_chunks(chunks=chunks, vectors=vectors, collection_name=col_name)
    assert stored_count == len(chunks)

    # 5. Verify collection info
    info = store.get_collection_info(col_name)
    assert info["points"] == len(chunks)
    assert info["vector_size"] == embedder.dimension

    # 6. Retrieve each chunk by its deterministic ID and verify payload completeness
    for chunk in chunks:
        payload = store.get_by_id(chunk.id, collection_name=col_name)
        assert payload is not None
        assert payload["chunk_id"] == chunk.id
        assert payload["file_path"] == chunk.file_path
        assert payload["symbol_name"] == chunk.symbol_name
        assert payload["symbol_type"] == chunk.symbol_type
        assert payload["code"] == chunk.code

    store.close()
