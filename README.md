# DevPilot

DevPilot is an AI-powered developer assistant (currently in early stages).

## Architecture

The DevPilot pipeline processes codebases deterministically and transforms syntax trees into persistent semantic vector spaces for natural-language code search:

```text
Indexing Pipeline:
Project -> Scanner -> Tree-sitter Parser -> CodeChunk -> Embedding Model -> Qdrant Collection (data/qdrant/)

Search Pipeline:
User Query
   ↓
Embedding Model (BAAI/bge-small-en-v1.5)
   ↓
Query Vector (384-d)
   ↓
Qdrant Vector Search (Cosine Similarity)
   ↓
Top-K Scored Points + Payload
   ↓
Ranked SearchResult Objects
```

---

## Features

### DevPilot v0.1 — Project Scanner
* Recursively scans a directory, discovers files, computes file metadata, and summarizes extensions.
* Filters out common ignored folders (e.g. `.git`, `venv`, `node_modules`).

### DevPilot v0.2 — Tree-sitter Python Parser
* Robust AST parsing using Tree-sitter.
* Extracts structured metadata from Python files: functions, classes, methods, and import statements with exact source lines.

### DevPilot v0.3 — Code Chunking & Metadata
* **Semantic Code Chunking**: Converts AST symbols into structured `CodeChunk` objects representing complete syntactic units (functions, classes, methods).
* **Deterministic Chunk IDs**: Stable SHA-256 hash computed from normalized file path, symbol type, parent symbol, symbol name, and line span.
* **Rich Metadata**: Captures language, file extension, and file-level imports for every chunk without duplicating import chunks.

### DevPilot v0.4 — Local Code Embeddings
* **Semantic Code Representations**: Converts structured `CodeChunk` objects into numerical vector embeddings capturing semantic meaning and intent.
* **Why Code Needs Embeddings**: Lexical search (grep/keyword) fails when queries use different synonyms or concepts (e.g., searching *"user verification"* won't match `authenticate_user`). Embeddings map semantically similar code concepts near each other in vector space.
* **Vector & Embedding Dimensions**: A vector is an array of floating-point numbers where each dimension encodes latent semantic features. The default model `BAAI/bge-small-en-v1.5` outputs dense 384-dimensional vectors.
* **Local Model Execution**: Runs 100% locally via `sentence-transformers` without requiring external APIs, credentials, or network calls during inference.
* **Vector Normalization & Distance Metric**: Vectors are $L_2$-normalized (`normalize_embeddings=True`), allowing cosine distance/similarity to compare vector directions accurately invariant to text length.
* **Local Development Index**: Serializes generated embeddings and chunk metadata to `data/embeddings/index.json`.

### DevPilot v0.5 — Qdrant Vector Database Integration
* **What is a Vector Database?**: A specialized database engineered to store, index, and query high-dimensional vector embeddings alongside rich structured payload metadata.
* **Why DevPilot Needs a Vector Database**: Flat files (such as JSON) require loading all vectors into memory and performing linear $O(N)$ scans. A vector database provides scalable, persistent, and indexed storage with fast lookups.
* **Why Qdrant is Used**:
  - High performance written in Rust with official Python client (`qdrant-client`).
  - Supports embedded local persistent disk mode without requiring an external server or Docker container.
  - Native payload filtering and metadata indexing.
  - Standardized distance metrics including Cosine, Euclidean, and Dot product.
* **Key Vector Database Concepts**:
  - **Collection**: A named, isolated set of points that share the same vector dimension and distance metric (`devpilot_code`).
  - **Point**: The core entity stored in Qdrant, consisting of a deterministic UUIDv5 ID, a dense vector, and payload metadata.
  - **Payload Metadata**: JSON payload attached to each point containing `chunk_id`, `file_path`, `language`, `symbol_name`, `symbol_type`, `parent_symbol`, `start_line`, `end_line`, `code`, and imports.
  - **Upsert**: Updates existing points in-place without duplicating records.
  - **Local Persistent Storage**: Stored on disk in `data/qdrant/`.

### DevPilot v0.6 — Semantic Code Search
* **What Semantic Search Means**: Finding code based on conceptual intent and meaning rather than exact string matching.
* **Why Keyword Search is Insufficient**: Keyword queries like *"how do we hash passwords?"* or *"verify login credentials"* fail with grep when the actual function is named `authenticate_user` or `hash_password`. Semantic search bridges the vocabulary gap.
* **Query Embedding**: The exact same `BAAI/bge-small-en-v1.5` model converts the query into a 384-dimensional vector in the same coordinate space as the indexed code.
* **Cosine Similarity**: Qdrant computes the cosine similarity between the query vector and stored vectors, returning scores between -1.0 and 1.0 (with higher scores indicating greater semantic similarity).
* **Configurable Top-K**: Controls the maximum number of ranked results returned (default: 5).
* **Minimum Score Cutoff (`--min-score`)**: Eliminates irrelevant results that fall below a specified similarity threshold.
* **Payload Filtering**:
  - `--extension`: Restrict search by file extension (e.g. `.py`).
  - `--path`: Restrict search to specific directories (e.g. `backend/`).
  - `--type`: Restrict search by symbol type (`function`, `class`, `method`).
* **Output Modes**: Formatted terminal output with exact line ranges and source snippets, or machine-readable JSON via `--json`.
* **Scope Boundaries**:
  - **RAG (Retrieval-Augmented Generation)**: *Future version*
  - **LLM Synthesis**: *Future version*
  - **AI Agent Execution**: *Future version*

---

## Installation

1. Clone or download this repository.
2. Ensure you have Python 3.10+ installed.
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

---

## Usage

Run the tool by using `app.main` as a module.

### CLI Help
```bash
python -m app.main --help
```

### 1. Scan Directory (v0.1)
```bash
python -m app.main scan .
```

### 2. Parse Python AST (v0.2)
```bash
python -m app.main parse .
# or for JSON:
python -m app.main parse . --json
```

### 3. Index Code Chunks (v0.3)
```bash
python -m app.main index .
# or for JSON:
python -m app.main index . --json
```

### 4. Generate Code Embeddings (v0.4)
```bash
python -m app.main embed .
```

### 5. Generate Query Embedding (v0.4)
```bash
python -m app.main embed-query "where is user authentication handled?"
```

### 6. Store Vectors in Qdrant (v0.5)
```bash
python -m app.main store .
```

### 7. Collection Information (v0.5)
```bash
python -m app.main store-info
```

### 8. Retrieve Point by Chunk ID (v0.5)
```bash
python -m app.main store-get <chunk_id>
```

### 9. Reset Collection (v0.5)
```bash
python -m app.main store-reset
```

### 10. Semantic Code Search (v0.6)
Search the indexed codebase using natural-language queries:

```bash
python -m app.main search "where is user authentication handled?"
```

Example output:
```text
DevPilot v0.6 - Semantic Code Search

Query:
where is user authentication handled?

Results:

[1] Score: 0.6618
File: sample_project\auth.py
Symbol: login_user
Type: function
Lines: 14-15

def login_user(username, password):
    pass

[2] Score: 0.6611
File: sample_project\auth.py
Symbol: __init__
Type: method
Class: AuthService
Lines: 5-6

def __init__(self):
        self.secret = os.getenv("SECRET_KEY", "default_secret")

[3] Score: 0.6603
File: sample_project\auth.py
Symbol: AuthService
Type: class
Lines: 4-12

class AuthService:
    def __init__(self):
        self.secret = os.getenv("SECRET_KEY", "default_secret")

    def hash_password(self, password):
        return hashlib.sha256((password + self.secret).encode()).hexdigest()

    def verify_password(self, password, hashed):
        return self.hash_password(password) == hashed

Found 3 relevant results.
```

#### Limit Results with Top-K:
```bash
python -m app.main search "password verification" --top-k 3
```

#### Filter by Symbol Type:
```bash
python -m app.main search "authentication" --type function
```

#### Filter by Directory Path or Extension:
```bash
python -m app.main search "authentication" --path sample_project/ --extension .py
```

#### Filter by Minimum Similarity Score:
```bash
python -m app.main search "authentication" --min-score 0.65
```

#### JSON Output:
```bash
python -m app.main search "where is user authentication handled?" --json
```

---

## Running Tests

Tests are written using `pytest`. All tests execute locally using in-memory or temporary disk storage without external network dependencies.
```bash
python -m pytest tests/
```

---

## Future Versions (Roadmap)
* **DevPilot v0.7+**: LLM / RAG Integration & Agentic Workflow
