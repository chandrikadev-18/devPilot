# DevPilot

DevPilot is an AI-powered developer assistant (currently in early stages).

## Architecture

The current pipeline processes codebases deterministically through structural analysis:

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
```

## Features

### DevPilot v0.1 — Project Scanner
* Recursively scans a directory, discovers files, computes file metadata, and summarizes extensions.
* Filters out common ignored folders (e.g. `.git`, `venv`, `node_modules`).

### DevPilot v0.2 — Tree-sitter Python Parser
* Robust AST parsing using Tree-sitter.
* Extracts structured metadata from Python files: functions, classes, methods, and import statements with exact source lines.

### DevPilot v0.3 — Code Chunking & Metadata
* **Semantic Code Chunking**: Converts AST symbols into structured `CodeChunk` objects representing complete syntactic units (functions, classes, methods).
* **Why Semantic Units**: Unlike arbitrary fixed-size character/token chunking (which cuts across function boundaries and breaks control flow), semantic units preserve full context, signature, docstrings, decorators, and implementation logic.
* **Deterministic Chunk IDs**: Each chunk is assigned a stable SHA-256 hash computed from its normalized file path, symbol type, parent symbol, symbol name, and line span.
* **Rich Metadata**: Captures language, file extension, and file-level imports for every chunk without duplicating import chunks.
* **Resilient Processing**: Gracefully handles parsing failures and syntax anomalies without crashing project indexing.

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

## Usage

Run the tool by using `app.main` as a module. It supports `scan`, `parse`, and `index` subcommands. If no subcommand is provided, it defaults to `scan`.

### CLI Help
```bash
python -m app.main --help
```

### 1. Scan Directory
```bash
python -m app.main .
# or
python -m app.main scan .
```

### 2. Parse Python Files
```bash
python -m app.main parse .
```
For JSON output:
```bash
python -m app.main parse . --json
```

### 3. Index Code Chunks (v0.3)
Scan, parse, and generate structured `CodeChunk` objects:
```bash
python -m app.main index .
```

Example summary output:
```text
DevPilot v0.3 - Code Indexer

Project: .

Python files analyzed: 6

Chunks created: 18

Functions: 10
Classes: 3
Methods: 5

Indexing completed successfully.
```

#### JSON Output
Export generated chunks and metadata as valid JSON:
```bash
python -m app.main index . --json
```

Example JSON structure:
```json
{
  "project": "sample_project",
  "total_chunks": 8,
  "chunks": [
    {
      "id": "e68969c89b3d9649a5b95fc6912d49d3b65f11d3a5d3a90abc64eac29e53d87f",
      "file_path": "auth.py",
      "language": "python",
      "symbol_name": "AuthService",
      "symbol_type": "class",
      "parent_symbol": null,
      "start_line": 4,
      "end_line": 12,
      "code": "class AuthService:\n    def __init__(self):\n        self.secret = os.getenv(\"SECRET_KEY\", \"default_secret\")\n\n    def hash_password(self, password):\n        return hashlib.sha256((password + self.secret).encode()).hexdigest()\n\n    def verify_password(self, password, hashed):\n        return self.hash_password(password) == hashed",
      "metadata": {
        "extension": ".py",
        "imports": [
          "import hashlib",
          "import os"
        ]
      }
    }
  ]
}
```

## Running Tests

Tests are written using `pytest`.
```bash
python -m pytest tests/
```

## Future Versions (Roadmap)
* Embeddings generation & Vector Store integration (e.g. Qdrant)
* Semantic code search and RAG retrieval
* LLM integration and agentic workflow orchestration
