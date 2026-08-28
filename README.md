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
* **Available Read-Only Code Tools**:
  1. `search_code`: Executes semantic similarity search across indexed code vectors (reuses v0.6).
  2. `read_file`: Reads text contents of a project file with security sandbox checks and truncation limits.
  3. `find_symbol`: Locates specific function, class, or method definitions across indexed metadata or AST.
  4. `get_file_structure`: Extracts AST overview (classes, functions, methods, imports) of a file without executing code.
* **Why Tools are Read-Only**: Security and safety guarantee. DevPilot cannot modify project files, execute code, run shell commands, access secrets, or make destructive changes.
* **Strict Path & Secret Security**: Path resolution strictly prevents directory traversal (`../`), blocks access to `.env` or `.git/` files, and confines file access to the designated project root.
* **Bounded Execution Limits**: Runaway loops are prevented with `MAX_AGENT_ITERATIONS` (default: 5) and `MAX_TOOL_CALLS` (default: 10), plus `MAX_TOOL_RESULT_CHARACTERS` (default: 12000).

### DevPilot v0.9 — Git Intelligence
* **Read-Only Git History Analysis**: Inspects repository commits, file modification histories, line-by-line authorship (blame), and patch diffs without altering repository state.
* **Commit Metadata**: Extracts commit SHA hashes (full and short), author name, email, commit timestamp (UTC), commit message, and changed file list.
* **File History & Evolution**: Traces when files were created or modified and lists historical commits affecting target files.
* **Line Blame Analysis**: Inspects exact line-level commit attribution with optional line range bounding (`--start-line`, `--end-line`).
* **Bounded Diff Inspection**: Safely inspects commit patch diffs with additions/deletions statistics and automatic truncation at `MAX_DIFF_CHARACTERS` (12,000 chars) marked with `[diff truncated]`.
* **Read-Only Git Tools for AI Agent**:
  1. `get_file_history`: Retrieves recent Git commits modifying a specific file.
  2. `get_recent_commits`: Retrieves recent Git commits across the repository.
  3. `get_last_commit`: Retrieves the most recent Git commit that modified a file.
  4. `get_commit`: Retrieves metadata and limited diff for a specific commit hash.
  5. `get_file_blame`: Shows commit and author attribution for specific lines.
* **Combined Code + Git Analysis**: The AI agent seamlessly combines semantic code search, AST symbol inspection, and Git history tools to answer questions such as:
  - "When was this function last changed?"
  - "Who changed this file?"
  - "What changed recently in auth.py?"
  - "Why was this function changed?" (grounded in commit messages and diff evidence)
* **Separate Source Citations**: Distinguishes Code Sources (`[Code Source]` file paths, symbols, line ranges) and Git Sources (`[Git Source]` commit hashes, authors, dates, messages).
* **Git Safety & Sandbox Guardrails**:
  - Strictly forbidden: `git commit`, `git push`, `git pull`, `git checkout`, `git reset`, `git merge`, `git rebase`, or branch creation.
  - Path traversal (`../`) and external repository access outside project directory are strictly blocked.

### DevPilot v1.6 — Git Intelligence Layer
* **Unified Symbol + Git Intelligence**: Seamlessly resolves symbols (e.g. `GraphBuilder.build`) to source files and AST line ranges, tracing commit history and line authorship.
* **New Agent Tools**:
  1. `git_last_change`: Pinpoints the author, date, short hash, and commit message that last changed a specific symbol or file.
  2. `git_history`: Queries chronological commit histories affecting symbols or files.
  3. `git_blame_symbol`: Performs line-by-line blame analysis targeted specifically at a symbol definition to identify primary contributors and line authorship.
  4. `git_show_commit`: Inspects commit metadata, additions, deletions, changed files, and diff summary for a specific commit SHA or revision.
* **Combined Git History + Impact Analysis**: Answers questions such as *"What changed around GraphBuilder.build and what could be affected?"* by combining Git change tracking with upstream/downstream dependency impact graphs.
* **REST API Endpoints**:
  - `GET /api/git/last-change?symbol=...`
  - `GET /api/git/history?symbol=...&limit=...`
  - `GET /api/git/blame?symbol=...`
  - `GET /api/git/commit/{commit}`
* **CLI Subcommands**:
  - `python -m app.main git-last-change "GraphBuilder.build"`
  - `python -m app.main git-history "GraphBuilder.build"`
  - `python -m app.main git-blame "GraphBuilder.build"`
  - `python -m app.main git-show <commit>`

### DevPilot v1.7 — Code Change Intelligence & Smart Impact Analysis
* **Git Changes to Symbol Mapping**: Analyzes Git commit diffs to pinpoint added, modified, deleted, and renamed AST symbols (functions, methods, classes) and changed line spans.
* **Dependency Graph Impact**: Traverses direct and indirect reverse dependencies to find all callers and dependent modules affected by a commit.
* **Deterministic Risk Scoring**: Transparent formula evaluates change severity (0–100 score, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` levels) based on symbol counts, deletions, dependency depths, module sensitivity, and test coverage.
* **Agent Change Tool**:
  - `analyze_code_change`: Evaluates commit diffs, changed symbols, impact, and risk score for autonomous agent reasoning.
* **REST API Endpoints**:
  - `POST /api/changes/analyze`
  - `GET /api/changes/analyze?commit=...`
* **CLI Subcommand**:
  - `python -m app.main change-analyze HEAD`
  - `python -m app.main change-analyze <commit> --json`

```text
Code Change Intelligence Architecture:

      Git Commit
          ↓
    Changed Symbols (AST parsing before vs after)
          ↓
    Dependency Graph (Static Callers / Dependents Traversal)
          ↓
    Impact Analysis (Direct/Indirect Callers & Impacted Files)
          ↓
    Deterministic Risk Score (0-100 & LOW/MEDIUM/HIGH/CRITICAL)
          ↓
    AI Agent Explanation
```

### DevPilot v1.8 — Semantic Code Intelligence
* **Natural Language Code Search**: Formulate questions using concepts, architecture, and intent (e.g. *"Where is authentication handled?"*, *"Find code related to database connections"*).
* **Hybrid Retrieval Engine**: Combines vector cosine similarity with exact/fuzzy AST symbol matching, filename weighting, and deterministic ranking.
* **Semantic Search + Dependency Graph**: Discovers primary implementation symbols and enriches results with callers, callees, and architectural relationships.
* **Agent Semantic Tool**:
  - `semantic_code_search`: Retrieves ranked code symbols, file locations, line ranges, and connected graph functionality.
* **REST API Endpoints**:
  - `POST /api/search/semantic` (body: `{"query": "...", "top_k": 5}`)
  - `GET /api/search/semantic?query=...&top_k=5`
* **CLI Subcommand**:
  - `python -m app.main semantic-search "database connection"`
  - `python -m app.main semantic-search "authentication" --json`

```text
Semantic Code Intelligence Architecture:

      Natural Language Query
                ↓
          Hybrid Search
         ┌──────┴──────┐
         ↓             ↓
      Symbol        Semantic
      Search         Search
         └──────┬──────┘
                ↓
         Relevant Symbols
                ↓
        Dependency Graph
                ↓
        Context Retrieval
                ↓
        Agent Explanation
```

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
python -m app.main git-log --help
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

### DevPilot v1.0 — Code Dependency & Relationship Graph
* **Static Code Dependency Graph**: Builds an in-memory directed graph of code entities and relationships extracted via Tree-sitter AST analysis.
* **Deterministic Node IDs**:
  - Files: `file:<file_path>` (e.g. `file:backend/auth.py`)
  - Classes: `class:<file_path>:<class_name>` (e.g. `class:backend/auth.py:AuthService`)
  - Functions: `function:<file_path>:<func_name>` (e.g. `function:backend/auth.py:login_user`)
  - Methods: `method:<file_path>:<class_name>.<method_name>` (e.g. `method:backend/auth.py:AuthService.login`)
  - Modules: `module:<module_name>` (e.g. `module:hashlib`)
* **Entity Relationships**:
  - `FILE -(CONTAINS)-> CLASS`
  - `FILE -(DEFINES)-> FUNCTION`
  - `CLASS -(CONTAINS)-> METHOD`
  - `METHOD -(BELONGS_TO)-> CLASS`
  - `FILE -(IMPORTS)-> FILE` / `MODULE`
  - `CALLER -(CALLS)-> CALLEE`
* **Deterministic Name Resolution**:
  1. Same class method (`self.method()` or method in current class)
  2. Same file top-level function
  3. Imported symbol (from `import` or `from ... import` statements)
  4. Unique matching project symbol
  5. Unresolved calls omit edges (no fake/hallucinated nodes).
* **Graph Query Engine & Impact Analysis**:
  - `get_callers`: Functions/methods calling a symbol.
  - `get_callees`: Functions/methods called by a symbol.
  - `get_dependencies`: Downstream multi-depth traversal with cycle prevention.
  - `get_impact`: Static impact analysis discovering all direct and indirect callers affected if a symbol is modified.
  - `get_file_dependencies`: File-level import dependencies and defined symbols.
* **Read-Only Graph Tools for AI Agent**:
  - `get_callers`, `get_callees`, `get_dependencies`, `get_impact`, `get_file_dependencies`.
* **Static Analysis Disclaimer**:
  - Dependency and call relationships are determined via static AST analysis without runtime execution. Dynamic dispatch, runtime reflection (`getattr`), or dynamic monkey-patching are not evaluated.

---

## CLI Usage

### 1. Project Scanner (v0.1)
```bash
python -m app.main scan .
```

### 2. Tree-sitter Python Parser (v0.2)
```bash
python -m app.main parse sample_project/auth.py
```

### 3. Code Chunking & Indexing (v0.3)
```bash
python -m app.main index sample_project/
```

### 4. Local Code Embeddings (v0.4)
```bash
python -m app.main embed sample_project/ --output data/embeddings/index.json
```

### 5. Qdrant Vector Storage (v0.5)
```bash
python -m app.main store sample_project/
python -m app.main store-info
```

### 6. Semantic Code Search (v0.6)
```bash
python -m app.main search "where is user authentication handled?"
```

### 7. Codebase Question Answering with RAG (v0.7)
```bash
python -m app.main ask "Where is user authentication handled?"
```

### 8. Git History & Intelligence (v0.9)

#### Show Recent Commits:
```bash
python -m app.main git-log --limit 5
```

#### Show Commit History for a File:
```bash
python -m app.main git-history app/config.py
```

#### Show Last Change for a File:
```bash
python -m app.main git-last-change app/config.py
```

#### Show Commit Details & Diff:
```bash
python -m app.main git-show HEAD
```

#### Show File Blame:
```bash
python -m app.main git-blame app/config.py --start-line 1 --end-line 25
```

### 9. Code Dependency Graph (v1.0)

#### Build Dependency Graph:
```bash
python -m app.main graph-build sample_project/ --output data/graph.json
```

#### Inspect Graph Statistics:
```bash
python -m app.main graph-info
```

#### Find Callers of a Function/Method:
```bash
python -m app.main graph-callers hash_password
```

#### Find Outgoing Calls from a Function/Method:
```bash
python -m app.main graph-callees verify_password
```

#### Downstream Dependency Traversal:
```bash
python -m app.main graph-dependencies login_user --depth 2
```

#### Static Impact Analysis:
```bash
python -m app.main graph-impact hash_password --depth 2
```

#### Inspect File Import Relationships:
```bash
python -m app.main graph-file-dependencies sample_project/auth.py
```

#### JSON Output Mode:
```bash
python -m app.main graph-info --json
python -m app.main graph-impact hash_password --json
```

### 10. Autonomous Codebase, Git & Graph AI Agent (v0.8 - v1.0)
Ask complex questions combining semantic search, Git history, and dependency graph relationships:

```bash
python -m app.main agent "What functions call hash_password and what could break if I change it?"
```

Example human-readable output:
```text
DevPilot v1.0 - Autonomous Codebase Agent

Question:
What functions call hash_password and what could break if I change it?

Final Answer:

Based on the static code dependency graph:
1. `hash_password` is directly called by `verify_password` in `sample_project/auth.py` at line 12.
2. If `hash_password` is modified, the direct impact is `verify_password`. Any callers of `verify_password` (such as authentication handlers) may also be impacted.

Sources:

1. [Graph Source] verify_password
   File:     auth.py
   Lines:    11-12
   Relation: CALLER

Agent iterations: 2
Tool calls: 2
Total time: 1.62s
```

#### Verbose Debug Mode:
```bash
python -m app.main agent "What are the dependencies of auth.py?" --debug
```

#### JSON Output Mode:
```bash
python -m app.main agent "Show callers of hash_password" --json
```

---

## Running Tests

Run all unit and mock integration tests using `pytest` without requiring an API key or internet access:

```bash
python -m pytest tests/
```

---

## Scope & Roadmap

| Feature Area | Status in v1.0 | Roadmap |
| :--- | :--- | :--- |
| **Project Scanner & Tree-sitter Parser** | Completed (v0.1 - v0.2) | Maintained |
| **Code Chunking & Local Embeddings** | Completed (v0.3 - v0.4) | Maintained |
| **Qdrant Vector Store & Semantic Search** | Completed (v0.5 - v0.6) | Maintained |
| **RAG & Single-Turn Codebase Q&A** | Completed (v0.7) | Maintained |
| **Read-Only Tool-Using AI Agent** | Completed (v0.8) | Maintained |
| **Read-Only Git Intelligence & History** | Completed (v0.9) | Maintained |
| **Code Dependency & Relationship Graph** | **Completed (v1.0)** | Maintained |
| **External Graph DB (Neo4j)** | Out of Scope for v1.0 | Future version |
| **Code Modification & File Editing** | Out of Scope | Future version |
| **Code Execution & Shell Commands** | Out of Scope | Strictly Forbidden |
| **Multi-Agent Systems** | Out of Scope | Future version |
