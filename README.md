# DevPilot

DevPilot is an AI-powered developer assistant (currently in early stages).

## Architecture

The DevPilot pipeline processes codebases deterministically and transforms syntax trees into semantic vector spaces:

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
Embedding Model (sentence-transformers)
   ↓
Vector Embeddings
   ↓
Local Development Index (data/embeddings/index.json)
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
* **Unified Model for Code & Query**: The identical embedding model is used for both code indexing (`code -> vector`) and search queries (`query -> vector`) ensuring they share the same semantic coordinate space.
* **Vector Normalization**: Vectors are $L_2$-normalized (`normalize_embeddings=True`), allowing cosine similarity to be computed efficiently via simple dot products.
* **Batch Processing**: Encodes chunks in configurable batches (default 32) with a single model load for optimal throughput.
* **Local Development Index**: Serializes generated embeddings and chunk metadata to `data/embeddings/index.json` for rapid local inspection.

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
Scan, parse, chunk, and embed all code symbols in the project into local vector storage:
```bash
python -m app.main embed .
```

Example output:
```text
DevPilot v0.4 - Code Embeddings

Project: .

Python files analyzed: 6
Code chunks: 18

Embedding model:
BAAI/bge-small-en-v1.5

Embedding dimension:
384

Embeddings generated:
18

Index saved:
data/embeddings/index.json

Performance:
  Model loading: 4.21s
  Chunk preparation: 0.02s
  Embedding generation: 1.87s
  Index saving: 0.03s
  Total: 6.13s

Embedding completed successfully.
```

### 5. Generate Query Embedding (v0.4)
Generate a vector representation for a natural-language search query:
```bash
python -m app.main embed-query "where is user authentication handled?"
```

Optionally view vector dimensions and preview values:
```bash
python -m app.main embed-query "where is user authentication handled?" --show-vector
```

---

## Running Tests

Tests are written using `pytest`.
```bash
python -m pytest tests/
```

---

## Future Versions (Roadmap)
* **DevPilot v0.5**: Qdrant / Vector Database Integration
* **DevPilot v0.6**: Semantic Search & Hybrid Retrieval
* **DevPilot v0.7+**: LLM / RAG Integration & Agentic Workflow
