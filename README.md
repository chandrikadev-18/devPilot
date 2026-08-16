# DevPilot

DevPilot is an AI-powered developer assistant (currently in early stages).

## Architecture

The DevPilot pipeline processes codebases deterministically and transforms syntax trees into persistent semantic vector spaces:

```text
Project
   ↓
Scanner
   ↓
Tree-sitter Parser
   ↓
Code Symbols
   ↓
CodeChunk
   ↓
Embedding Model (BAAI/bge-small-en-v1.5)
   ↓
Embedding Vector (384-d)
   ↓
Qdrant Collection (devpilot_code)
   ↓
Vector + Payload Metadata (data/qdrant/)
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
  - **Collection**: A named, isolated set of points that share the same vector dimension and distance metric (e.g. `devpilot_code` with dimension 384 and Cosine distance).
  - **Point**: The core entity stored in Qdrant, consisting of a unique ID, a dense vector, and optional JSON payload metadata.
  - **Vector**: A dense array of 384 floating-point numbers encoding the semantic meaning of the code snippet.
  - **Payload Metadata**: JSON payload attached to each point containing `chunk_id`, `file_path`, `language`, `symbol_name`, `symbol_type`, `parent_symbol`, `start_line`, `end_line`, `code`, and import metadata.
  - **Deterministic IDs**: Chunk IDs are mapped to reproducible UUIDv5 identifiers. Re-indexing identical code produces the exact same point ID.
  - **Upsert**: Insert or update operation. If a point with the same ID already exists, its vector and payload are updated in place, preventing duplicate points during re-indexing.
  - **Local Persistent Storage**: Vectors and payloads are stored on disk in `data/qdrant/` for development without cloud lock-in or network dependencies.
* **Scope Notice**:
  - **Semantic Search**: *Coming in v0.6*
  - **RAG (Retrieval-Augmented Generation)**: *Future version*
  - **AI Agent & LLMs**: *Future version*

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
Scan, parse, chunk, embed, and store all code chunks in local Qdrant vector database:
```bash
python -m app.main store .
```

Example output:
```text
DevPilot v0.5 - Vector Store

Project: .

Python files analyzed: 20
Code chunks: 111

Embedding model:
BAAI/bge-small-en-v1.5

Embedding dimension:
384

Qdrant collection:
devpilot_code

Vectors stored:
111

Storage:
data/qdrant/

Performance:
  Scanner: 0.00s
  Parser: 0.02s
  Chunking: 0.00s
  Embedding: 40.57s
  Qdrant: 0.24s
  Upsert: 0.83s
  Total: 41.67s

Vector storage completed successfully.
```

### 7. Collection Information (v0.5)
Display current collection status, point count, and dimension:
```bash
python -m app.main store-info
```

Example output:
```text
DevPilot v0.5 - Vector Store Information

Collection:
devpilot_code

Vector dimension:
384

Distance:
Cosine

Points:
111

Status:
Ready
```

### 8. Retrieve Point by Chunk ID (v0.5)
Inspect stored payload and source line spans for a specific chunk ID:
```bash
python -m app.main store-get <chunk_id>
```

Example output:
```text
Chunk ID:
a91d0135e2e0cfeda8dcc3abe1a258a216da8e0333f7dc441f0da895f7f8aea9

File:
app\embeddings\embedder.py

Symbol:
build_embedding_text

Type:
function

Lines:
11-38
```

### 9. Reset Collection (v0.5)
Safely delete the vector collection with interactive confirmation:
```bash
python -m app.main store-reset
```

---

## Running Tests

Tests are written using `pytest`. All tests execute locally using in-memory or temporary disk storage without external network dependencies.
```bash
python -m pytest tests/
```

---

## Future Versions (Roadmap)
* **DevPilot v0.6**: Semantic Search & Similarity Retrieval
* **DevPilot v0.7+**: LLM / RAG Integration & Agentic Workflow
