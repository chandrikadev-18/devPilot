# DevPilot

DevPilot is an AI-powered developer assistant for intelligent codebase exploration, semantic search, and autonomous read-only tool-using question answering.

## Architecture

The DevPilot pipeline processes codebases deterministically and combines dense vector search, retrieval-augmented generation (RAG), and an autonomous tool-using AI Agent:

```text
Indexing Pipeline (v0.1 - v0.5):
Project -> Scanner -> Tree-sitter Parser -> CodeChunk -> Embedding Model -> Qdrant Collection (data/qdrant/)

RAG Codebase Q&A Pipeline (v0.6 - v0.7):
User Question -> Semantic Search -> Top-K Chunks -> Context Builder -> LLM Prompt -> Answer + Sources

Autonomous AI Agent Pipeline (v0.8):
User Question
      ↓
Agent Orchestration Loop (Bounded Iterations & Tool-Call Limits)
      ↓
LLM Reasoning & Tool Call Decision
      ↓
Tool Registry Validation (Strict Input Schema & Read-Only Safety)
      ↓
Read-Only Codebase Tools (search_code, read_file, find_symbol, get_file_structure)
      ↓
Structured Tool Results & Verified Source Citations
      ↓
LLM Synthesis & Multi-Step Reasoning
      ↓
Final Grounded Answer + Separate Source Citations
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
* **Retrieval-Augmented Generation**: Retrieves exact code chunks matching user queries and constructs structured, token-bounded context blocks.
* **Strict Anti-Hallucination Guardrails**: Instructs the LLM to strictly base answers on retrieved context and acknowledge when context is insufficient.
* **Source Citations**: Preserves and outputs source files, symbol names, line numbers, and similarity scores alongside answers.

### DevPilot v0.8 — Tool-Using Codebase AI Agent
* **What is an AI Agent?**: Unlike a single-turn LLM or fixed RAG pipeline that only retrieves once, an AI Agent can dynamically reason, choose actions, inspect findings, and decide if further tool calls are required before formulating an answer.
* **Difference Between an LLM and an Agent**:
  - **LLM**: A static text generation model that takes input and returns a completion in one step.
  - **Agent**: An orchestration system wrapped around an LLM that maintains conversational state, calls external tools, inspects tool outputs, and loops iteratively until sufficient evidence is gathered.
* **What is a Tool?**: A strictly typed, callable Python function registered in the `ToolRegistry` with a validated JSON Schema input specification.
* **Available Read-Only Tools**:
  1. `search_code`: Executes semantic similarity search across indexed code vectors (reuses v0.6).
  2. `read_file`: Reads text contents of a project file with security sandbox checks and truncation limits.
  3. `find_symbol`: Locates specific function, class, or method definitions across indexed metadata or AST.
  4. `get_file_structure`: Extracts AST overview (classes, functions, methods, imports) of a file without executing code.
* **Why Tools are Read-Only**: Security and safety guarantee. DevPilot v0.8 cannot modify project files, execute code, run shell commands, access secrets, or make destructive changes.
* **Strict Path & Secret Security**: Path resolution strictly prevents directory traversal (`../`), blocks access to `.env` or `.git/` files, and confines file access to the designated project root.
* **Bounded Execution Limits**: Runaway loops are prevented with `MAX_AGENT_ITERATIONS` (default: 5) and `MAX_TOOL_CALLS` (default: 10), plus `MAX_TOOL_RESULT_CHARACTERS` (default: 12000).

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

4. Configure Environment Variables:
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
   MAX_AGENT_ITERATIONS=5
   MAX_TOOL_CALLS=10
   MAX_TOOL_RESULT_CHARACTERS=12000
   ```

---

## Usage

Run DevPilot using `app.main` as a module.

### CLI Help
```bash
python -m app.main --help
python -m app.main agent --help
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
```bash
python -m app.main ask "Where is user authentication handled?"
```

### 8. Tool-Using AI Agent (v0.8)
Ask complex questions and let the agent dynamically inspect the codebase:

```bash
python -m app.main agent "Where is authentication handled and what functions are in that file?"
```

Example human-readable output:
```text
DevPilot v0.8 - Codebase Agent

Question:
Where is authentication handled and what functions are in that file?

Agent:

Tool:
search_code

Query:
authentication handling

Results:
sample_project/auth.py
AuthService()

Tool:
get_file_structure

File:
sample_project/auth.py

Results:
sample_project/auth.py
AuthService()

Final Answer:

Authentication is handled in `sample_project/auth.py` within the `AuthService` class.

The file contains the following components:
- Class `AuthService`:
  - `__init__()` (lines 5-6)
  - `hash_password()` (lines 8-9)
  - `verify_password()` (lines 11-12)
- Function `login_user()` (lines 14-15)

Sources:

1. sample_project/auth.py
   AuthService()
   Lines: 4-12
   Score: 0.7420

2. sample_project/auth.py
   login_user()
   Lines: 14-15

Agent iterations: 2
Tool calls: 2
Total time: 1.65s
```

#### Verbose Debug Mode:
```bash
python -m app.main agent "How does login work?" --debug
```

#### JSON Output Mode:
```bash
python -m app.main agent "Where is authentication handled?" --json
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

| Feature Area | Status in v0.8 | Roadmap |
| :--- | :--- | :--- |
| **Project Scanner & Tree-sitter Parser** | Completed (v0.1 - v0.2) | Maintained |
| **Code Chunking & Local Embeddings** | Completed (v0.3 - v0.4) | Maintained |
| **Qdrant Vector Store & Semantic Search** | Completed (v0.5 - v0.6) | Maintained |
| **RAG & Single-Turn Codebase Q&A** | Completed (v0.7) | Maintained |
| **Read-Only Tool-Using AI Agent** | **Completed (v0.8)** | Maintained |
| **Code Modification & File Editing** | Out of Scope | Future version |
| **Code Execution & Shell Commands** | Out of Scope | Future version |
| **VS Code Extension & React UI** | Out of Scope | Future version |
| **Multi-Agent Systems** | Out of Scope | Future version |
