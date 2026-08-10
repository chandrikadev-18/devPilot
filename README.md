# DevPilot v0.1 - Project Scanner

DevPilot v0.1 is a lightweight Python command-line tool that recursively scans a software project directory and collects basic information about the repository. It ignores common unnecessary directories (like `.git`, `node_modules`, `venv`, etc.) to provide accurate and fast project statistics.

## Features
- Recursively scans directories to discover files.
- Ignores typical build/environment directories.
- Extracts file metadata (relative path, absolute path, name, extension, size).
- Computes project statistics (total files, total directories, extensions breakdown).
- Graceful error handling for missing directories or permission issues.

## Installation

1. Clone or download this repository.
2. Ensure you have Python 3.10+ installed.
3. (Optional) Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   
   pip install -r requirements.txt
   ```

## Usage

Run the scanner by passing a directory path to the main module:

```bash
python -m app.main ./sample_project
```

You can also use the help flag to see available options:

```bash
python -m app.main --help
```

### Example Output
```
Project: sample_project

Files: 15
Directories: 6

Extensions:
.py      8
.js      3
.md      2
.json    2
```

## Running Tests

Tests are written using `pytest`. To run them, ensure you are in the project root and execute:

```bash
pytest tests/
```
