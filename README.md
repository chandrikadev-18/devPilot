# DevPilot

DevPilot is an AI-powered developer assistant (currently in early stages).

## Features

### DevPilot v0.1
* Project Scanner: Recursively scans a directory, discovers files, computes file metadata, and summarizes extensions.

### DevPilot v0.2
* Tree-sitter Python Parser: Extracts AST metadata from Python files, including functions, classes, methods, and imports.

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

Run the tool by using `app.main` as a module. It supports `scan` and `parse` subcommands. If no subcommand is provided, it defaults to `scan`.

### Help
```bash
python -m app.main --help
```

### Scan Directory
```bash
python -m app.main .
# or
python -m app.main scan .
```

### Parse Python Files
```bash
python -m app.main parse .
```
For JSON output:
```bash
python -m app.main parse . --json
```

## Running Tests

Tests are written using `pytest`.
```bash
python -m pytest tests/
```
