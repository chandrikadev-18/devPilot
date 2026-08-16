import json
import pytest
from pathlib import Path
from qdrant_client.models import Distance

from app.embeddings.embedder import CodeEmbedder, DEFAULT_EMBEDDING_MODEL
from app.indexer.chunker import CodeChunk, CodeChunker
from app.parser.python_parser import PythonParser
from app.scanner.scanner import ProjectScanner
from app.search.semantic_search import SearchResult, SemanticSearcher
from app.vector_store.qdrant_store import (
    ConfigurationMismatchError,
    QdrantVectorStore,
    ValidationError,
    VectorStoreError,
)


@pytest.fixture(scope="module")
def embedder():
    """Module-scoped embedder fixture to reuse model across tests."""
    return CodeEmbedder(model_name=DEFAULT_EMBEDDING_MODEL)


@pytest.fixture
def mock_search_setup(embedder):
    """Sets up an in-memory Qdrant store with controlled multi-domain code chunks."""
    store = QdrantVectorStore(location=":memory:")
    col_name = "test_search_col"
    store.create_collection(collection_name=col_name, vector_size=embedder.dimension)

    chunks = [
        CodeChunk(
            id="chunk-auth-1",
            file_path="backend/auth.py",
            language="python",
            symbol_name="authenticate_user",
            symbol_type="function",
            parent_symbol=None,
            start_line=10,
            end_line=20,
            code="def authenticate_user(username, password):\n    \"\"\"Validates user credentials against database and issues JWT.\"\"\"\n    return check_password(username, password)",
            metadata={"extension": ".py", "imports": ["jwt", "hashlib"]},
        ),
        CodeChunk(
            id="chunk-auth-cls",
            file_path="backend/auth_service.py",
            language="python",
            symbol_name="AuthService",
            symbol_type="class",
            parent_symbol=None,
            start_line=1,
            end_line=30,
            code="class AuthService:\n    \"\"\"Handles user session management, OAuth2 login, and authentication tokens.\"\"\"\n    pass",
            metadata={"extension": ".py", "imports": ["requests"]},
        ),
        CodeChunk(
            id="chunk-pay-1",
            file_path="services/payment.py",
            language="python",
            symbol_name="process_payment",
            symbol_type="function",
            parent_symbol=None,
            start_line=15,
            end_line=25,
            code="def process_payment(customer_id, amount_cents, currency='USD'):\n    \"\"\"Charges credit card via Stripe payment gateway.\"\"\"\n    return stripe.Charge.create(customer=customer_id, amount=amount_cents)",
            metadata={"extension": ".py", "imports": ["stripe"]},
        ),
        CodeChunk(
            id="chunk-email-1",
            file_path="notifications/email_service.py",
            language="python",
            symbol_name="send_welcome_email",
            symbol_type="function",
            parent_symbol=None,
            start_line=5,
            end_line=15,
            code="def send_welcome_email(recipient_email, username):\n    \"\"\"Sends onboarding email with verification link via SMTP.\"\"\"\n    smtp_client.send(to=recipient_email, subject='Welcome!')",
            metadata={"extension": ".py", "imports": ["smtplib"]},
        ),
        CodeChunk(
            id="chunk-db-1",
            file_path="database/connection.py",
            language="python",
            symbol_name="connect_database",
            symbol_type="function",
            parent_symbol=None,
            start_line=8,
            end_line=18,
            code="def connect_database(database_uri):\n    \"\"\"Establishes connection pool to PostgreSQL database.\"\"\"\n    return psycopg2.connect(database_uri)",
            metadata={"extension": ".py", "imports": ["psycopg2"]},
        ),
    ]

    vectors = embedder.embed_chunks(chunks)
    store.upsert_chunks(chunks=chunks, vectors=vectors, collection_name=col_name)

    searcher = SemanticSearcher(
        embedder=embedder,
        vector_store=store,
        collection_name=col_name,
    )
    yield searcher, chunks
    store.close()


def test_query_embedding_and_search_returns_results(mock_search_setup):
    """Verify that a query returns SearchResult objects with required fields."""
    searcher, _ = mock_search_setup
    results = searcher.search("how to verify user login and password credentials?", top_k=3)

    assert len(results) > 0
    assert len(results) <= 3
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.chunk_id
        assert isinstance(r.score, float)
        assert r.file_path
        assert r.symbol_name
        assert r.symbol_type
        assert r.code
        assert isinstance(r.metadata, dict)


def test_results_sorted_by_relevance(mock_search_setup):
    """Verify that returned results are sorted descending by similarity score."""
    searcher, _ = mock_search_setup
    results = searcher.search("user authentication login", top_k=5)

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_k_parameter(mock_search_setup):
    """Verify top_k limit controls the number of results returned."""
    searcher, _ = mock_search_setup
    res_1 = searcher.search("code", top_k=1)
    assert len(res_1) == 1

    res_2 = searcher.search("code", top_k=2)
    assert len(res_2) == 2


def test_min_score_threshold(mock_search_setup):
    """Verify min_score filters out results with low similarity."""
    searcher, _ = mock_search_setup
    # With a high threshold, only very relevant items match
    high_threshold_results = searcher.search("credit card billing charge", min_score=0.999)
    assert len(high_threshold_results) == 0

    valid_results = searcher.search("credit card billing charge", min_score=0.4)
    assert len(valid_results) > 0
    for r in valid_results:
        assert r.score >= 0.4


def test_empty_query_rejected(mock_search_setup):
    """Verify empty and whitespace-only queries raise ValidationError."""
    searcher, _ = mock_search_setup
    with pytest.raises(ValidationError):
        searcher.search("")

    with pytest.raises(ValidationError):
        searcher.search("   ")


def test_no_indexed_collection_handled_gracefully(embedder):
    """Verify missing or empty collection raises VectorStoreError with clear message."""
    store = QdrantVectorStore(location=":memory:")
    searcher = SemanticSearcher(embedder=embedder, vector_store=store, collection_name="nonexistent")

    with pytest.raises(VectorStoreError) as exc_info:
        searcher.search("any query")
    assert "No indexed code found" in str(exc_info.value)
    store.close()


def test_extension_filtering(mock_search_setup):
    """Verify extension filtering restricts matches."""
    searcher, _ = mock_search_setup
    # All our chunks have .py
    py_results = searcher.search("authentication", extension=".py")
    assert len(py_results) > 0
    for r in py_results:
        assert r.file_path.endswith(".py")

    # Non-matching extension returns 0 results
    js_results = searcher.search("authentication", extension=".js")
    assert len(js_results) == 0


def test_path_filtering(mock_search_setup):
    """Verify path prefix filtering restricts matches to specific folders."""
    searcher, _ = mock_search_setup
    backend_results = searcher.search("system functionality", path_prefix="backend/")
    assert len(backend_results) > 0
    for r in backend_results:
        assert "backend/" in r.file_path.replace("\\", "/")

    notif_results = searcher.search("system functionality", path_prefix="notifications/")
    assert len(notif_results) > 0
    for r in notif_results:
        assert "notifications/" in r.file_path.replace("\\", "/")


def test_symbol_type_filtering(mock_search_setup):
    """Verify symbol_type filtering returns only matching symbol types."""
    searcher, _ = mock_search_setup
    class_results = searcher.search("authentication", symbol_type="class")
    assert len(class_results) > 0
    for r in class_results:
        assert r.symbol_type == "class"
        assert r.symbol_name == "AuthService"

    func_results = searcher.search("authentication", symbol_type="function")
    assert len(func_results) > 0
    for r in func_results:
        assert r.symbol_type == "function"


def test_json_serialization(mock_search_setup):
    """Verify SearchResult serialization to dict and JSON."""
    searcher, _ = mock_search_setup
    results = searcher.search("database connection", top_k=2)
    assert len(results) > 0

    as_dict = [r.to_dict() for r in results]
    json_str = json.dumps({"query": "database connection", "results": as_dict})
    parsed = json.loads(json_str)

    assert parsed["query"] == "database connection"
    assert len(parsed["results"]) == len(results)
    assert parsed["results"][0]["symbol_name"] == "connect_database"


def test_embedding_dimension_mismatch_detected(embedder):
    """Verify dimension mismatch between model and collection raises ConfigurationMismatchError."""
    store = QdrantVectorStore(location=":memory:")
    col_name = "mismatched_search_col"
    # Create collection with dimension 128 (while model is 384)
    store.create_collection(collection_name=col_name, vector_size=128)

    # Insert a dummy point so collection is not considered empty
    from qdrant_client.models import PointStruct
    store.client.upsert(
        collection_name=col_name,
        points=[PointStruct(id="00000000-0000-0000-0000-000000000001", vector=[0.1] * 128, payload={"chunk_id": "c1", "file_path": "a.py"})]
    )

    searcher = SemanticSearcher(embedder=embedder, vector_store=store, collection_name=col_name)
    with pytest.raises(ConfigurationMismatchError) as exc_info:
        searcher.search("test query")
    assert "Embedding configuration mismatch" in str(exc_info.value)
    store.close()


def test_semantic_ranking_behavior(mock_search_setup):
    """
    Controlled semantic domain ranking tests:
    - Authentication query ranks authenticate_user top
    - Payment query ranks process_payment top
    - Email query ranks send_welcome_email top
    """
    searcher, _ = mock_search_setup

    # 1. Auth query
    res_auth = searcher.search("How does the application verify a user's login credentials?", top_k=1)
    assert len(res_auth) == 1
    assert res_auth[0].symbol_name in ["authenticate_user", "AuthService"]

    # 2. Payment query
    res_pay = searcher.search("Where are payments processed and credit cards charged?", top_k=1)
    assert len(res_pay) == 1
    assert res_pay[0].symbol_name == "process_payment"

    # 3. Email query
    res_email = searcher.search("How does the application send welcome emails to users?", top_k=1)
    assert len(res_email) == 1
    assert res_email[0].symbol_name == "send_welcome_email"


def test_full_search_pipeline_integration(tmp_path, embedder):
    """
    End-to-end integration test:
    sample_project -> scanner -> parser -> chunker -> embedder -> Qdrant -> SemanticSearcher
    """
    sample_dir = Path("sample_project")
    if not sample_dir.exists():
        pytest.skip("sample_project directory not found")

    # 1. Scan
    scanner = ProjectScanner()
    files, _ = scanner.scan(str(sample_dir))
    python_files = [f for f in files if f.extension == ".py"]

    # 2. Parse & Chunk
    parser = PythonParser()
    chunker = CodeChunker()
    all_chunks = []
    for f in python_files:
        parsed = parser.parse_file(f.absolute_path)
        if "error" not in parsed:
            all_chunks.extend(chunker.chunk_parsed_file(parsed, file_path_override=f.relative_path))

    assert len(all_chunks) > 0

    # 3. Embed
    vectors = embedder.embed_chunks(all_chunks)

    # 4. Store in temporary Qdrant disk store
    qdrant_dir = tmp_path / "integration_search_qdrant"
    store = QdrantVectorStore(storage_path=str(qdrant_dir))
    col_name = "integration_search_col"
    store.create_collection(col_name, vector_size=embedder.dimension)
    store.upsert_chunks(all_chunks, vectors, collection_name=col_name)

    # 5. Semantic Search
    searcher = SemanticSearcher(embedder=embedder, vector_store=store, collection_name=col_name)
    results = searcher.search("user authentication login verification", top_k=3)

    assert len(results) > 0
    top_result = results[0]
    assert top_result.score > 0.0
    assert top_result.file_path
    assert top_result.symbol_name
    assert top_result.code

    store.close()
