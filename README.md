# DevPilot

DevPilot is an AI-powered developer assistant for intelligent codebase exploration and question answering.

## Architecture

The DevPilot pipeline processes codebases deterministically and combines dense vector search with retrieval-augmented generation (RAG):

```text
Indexing Pipeline (v0.1 - v0.5):
Project -> Scanner -> Tree-sitter Parser -> CodeChunk -> Embedding Model -> Qdrant Collection (data/qdrant/)

RAG Codebase Q&A Pipeline (v0.6 - v0.7):
User Question
      ↓
Query Embedding (BAAI/bge-small-en-v1.5)
      ↓
Semantic Search (Qdrant Cosine Similarity)
      ↓
Top-K Relevant CodeChunks
      ↓
Context Builder (Chunk & Character Limits, Source Metadata)
      ↓
LLM Prompt (System Guardrails + Grounded Context)
      ↓
LLM Provider (Groq / Configurable Abstraction)
      ↓
Grounded Answer + Separate Source Citations
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
* **Dense 384-dimensional Vectors**: Uses `BAAI/bge-small-en-v1.5` running locally via `sentence-transformers` without external API dependencies during inference.
* **Vector Normalization & Distance Metric**: Embeddings are $L_2$-normalized (`normalize_embeddings=True`) for cosine similarity.

### DevPilot v0.5 — Qdrant Vector Database Integration
* **Embedded Vector Database**: High-performance persistent storage on disk (`data/qdrant/`) via `qdrant-client`.
* **Payload Metadata**: Each stored point retains full code chunk metadata (`chunk_id`, `file_path`, `symbol_name`, `symbol_type`, `parent_symbol`, `start_line`, `end_line`, `code`).
* **Upsert Support**: Re-indexing updates existing points in place without duplicate records.

### DevPilot v0.6 — Semantic Code Search
* **Intent-Based Search**: Natural language queries matched via cosine similarity in Qdrant.
* **Top-K & Score Filtering**: Configurable result limit (`--top-k`) and relevance threshold (`--min-score`).
* **Payload Filters**: Filter by extension (`--extension`), directory path (`--path`), or symbol type (`--type`).

### DevPilot v0.7 — RAG + LLM Codebase Question Answering
* **What is RAG?**: Retrieval-Augmented Generation (Retrieval $\rightarrow$ Augmented Context $\rightarrow$ Generation). Instead of asking an LLM to guess repository implementation details from general training memory, RAG first retrieves the exact code snippets from the indexed codebase, injects them into the prompt as factual context, and instructs the LLM to generate an answer grounded strictly in that code.
* **Why Retrieval is Needed Before Generation**:
  - LLMs have no prior knowledge of private or recent codebases.
  - Sending the entire codebase in every prompt is impossible and expensive.
  - Semantic retrieval selects only the most relevant functions and classes for the question.
* **Reusing Semantic Search**: DevPilot v0.7 reuses the high-speed Qdrant vector search from v0.6 directly—no redundant search systems.
* **Structured Context Builder**: Converts retrieved `SearchResult` objects into clean context blocks while strictly enforcing chunk count (`MAX_CONTEXT_CHUNKS`) and character limits (`MAX_CONTEXT_CHARACTERS`) to prevent prompt overflow.
* **Strict Anti-Hallucination Guardrails**: Prompts instruct the LLM to only answer using provided code, to acknowledge when context is insufficient, and never invent non-existent files or functions.
* **Verified Source Citations**: File paths, symbol names, and line spans are preserved from actual search results and displayed alongside LLM answers.
* **Pluggable LLM Provider Abstraction**: Supports Groq (default) with clean error handling, bounded retries, and decoupled interfaces for future providers.

---

## Installation & Setup

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

4. Configure Environment Variables (Optional / for Live LLM):
   Copy `.env.example` to `.env` and configure your API key:
   ```bash
   cp .env.example .env
   ```
   Example configuration:
   ```dotenv
   LLM_PROVIDER=groq
   LLM_MODEL=llama-3.3-70b-versatile
   LLM_API_KEY=gsk_your_groq_api_key_here
   MAX_CONTEXT_CHUNKS=5
   MAX_CONTEXT_CHARACTERS=20000
   ```

---

## Usage

Run DevPilot using `app.main` as a module.

### CLI Help
```bash
python -m app.main --help
python -m app.main ask --help
```

### 1. Scan Directory (v0.1)
```bash
python -m app.main scan .
```

### 2. Parse Python AST (v0.2)
```bash
python -m app.main parse .
```

### 3. Index Code Chunks (v0.3)
```bash
python -m app.main index .
```

### 4. Generate Local Embeddings (v0.4)
```bash
python -m app.main embed .
```

### 5. Store Vectors in Qdrant (v0.5)
```bash
python -m app.main store sample_project/
```

### 6. Semantic Code Search (v0.6)
```bash
python -m app.main search "where is user authentication handled?"
```

### 7. Codebase Question Answering with RAG (v0.7)
Ask natural language questions about your codebase:

```bash
python -m app.main ask "Where is user authentication handled and how does password hashing work?"
```

Example human-readable output:
```text
DevPilot v0.7 - Codebase Q&A

Question:
Where is user authentication handled and how does password hashing work?

Answer:

Authentication is handled in `sample_project/auth.py` through the `AuthService` class and the `login_user()` function.

Password hashing is implemented inside `AuthService.hash_password()` (lines 8-9), which hashes the input password combined with a secret key using SHA-256 (`hashlib.sha256((password + self.secret).encode()).hexdigest()`).

Password verification is performed by `AuthService.verify_password()` (lines 11-12), which checks if the newly computed hash matches the stored hash.

Sources:

1. sample_project/auth.py
   AuthService()
   Lines: 4-12
   Score: 0.7420

2. sample_project/auth.py
   login_user()
   Lines: 14-15
   Score: 0.7105

Search time: 0.08s
LLM time: 1.12s
Total time: 1.20s
```

#### JSON Output Mode:
```bash
python -m app.main ask "where is user authentication handled?" --json
```

#### Filter by Directory or Symbol Type:
```bash
python -m app.main ask "how are users retrieved?" --path sample_project/ --top-k 3
```

---

## Running Tests

Run all unit and mock integration tests using `pytest` without requiring an API key or internet access:

```bash
python -m pytest tests/
```

### Running Opt-In Real LLM Tests:
```bash
RUN_LLM_INTEGRATION_TESTS=1 LLM_API_KEY=your_key pytest tests/test_rag.py -k test_real_groq_provider_live
```

---

## Scope & Roadmap

| Feature Area | Status in v0.7 | Roadmap |
| :--- | :--- | :--- |
| **Project Scanner & Tree-sitter Parser** | Completed (v0.1 - v0.2) | Maintained |
| **Code Chunking & Local Embeddings** | Completed (v0.3 - v0.4) | Maintained |
| **Qdrant Vector Store & Semantic Search** | Completed (v0.5 - v0.6) | Maintained |
| **RAG & Grounded Codebase Q&A** | **Completed (v0.7)** | Maintained |
| **AI Agents & Autonomous Workflows** | Out of Scope | Future version |
| **Tool Calling & Execution** | Out of Scope | Future version |
| **Code Modification & File Editing** | Out of Scope | Future version |
| **VS Code Extension & React UI** | Out of Scope | Future version |
