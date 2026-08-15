import json
import pytest
from pathlib import Path
from app.parser.python_parser import PythonParser
from app.indexer.chunker import CodeChunk, CodeChunker, generate_chunk_id


@pytest.fixture
def parser():
    return PythonParser()


@pytest.fixture
def chunker():
    return CodeChunker()


@pytest.fixture
def sample_dir():
    return Path(__file__).parent.parent / "sample_project"


def test_function_chunk(parser, chunker, sample_dir):
    """Verify function chunk properties: name, type, code, line numbers, file path."""
    auth_file = sample_dir / "auth.py"
    parsed = parser.parse_file(auth_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override="sample_project/auth.py")

    fn_chunks = [c for c in chunks if c.symbol_type == "function"]
    assert len(fn_chunks) == 1

    fn = fn_chunks[0]
    assert fn.symbol_name == "login_user"
    assert fn.symbol_type == "function"
    assert fn.parent_symbol is None
    assert fn.start_line == 14
    assert fn.end_line == 15
    assert "def login_user(username, password):" in fn.code
    assert fn.file_path == "sample_project/auth.py"
    assert fn.language == "python"


def test_class_chunk(parser, chunker, sample_dir):
    """Verify class chunk properties: class name, type, code, line numbers."""
    auth_file = sample_dir / "auth.py"
    parsed = parser.parse_file(auth_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override="sample_project/auth.py")

    class_chunks = [c for c in chunks if c.symbol_type == "class"]
    assert len(class_chunks) == 1

    cls = class_chunks[0]
    assert cls.symbol_name == "AuthService"
    assert cls.symbol_type == "class"
    assert cls.parent_symbol is None
    assert cls.start_line == 4
    assert cls.end_line == 12
    assert "class AuthService:" in cls.code
    assert "def hash_password" in cls.code


def test_method_chunk(parser, chunker, sample_dir):
    """Verify method chunk properties: method name, type, parent class, code, line numbers."""
    auth_file = sample_dir / "auth.py"
    parsed = parser.parse_file(auth_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override="sample_project/auth.py")

    method_chunks = [c for c in chunks if c.symbol_type == "method"]
    assert len(method_chunks) == 3

    method_names = {m.symbol_name: m for m in method_chunks}
    assert "__init__" in method_names
    assert "hash_password" in method_names
    assert "verify_password" in method_names

    hash_method = method_names["hash_password"]
    assert hash_method.symbol_type == "method"
    assert hash_method.parent_symbol == "AuthService"
    assert hash_method.start_line == 8
    assert hash_method.end_line == 9
    assert "def hash_password(self, password):" in hash_method.code


def test_chunk_metadata(parser, chunker, sample_dir):
    """Verify metadata contains extension, imports, and chunk retains language and file path."""
    auth_file = sample_dir / "auth.py"
    parsed = parser.parse_file(auth_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override="sample_project/auth.py")

    for chunk in chunks:
        assert chunk.language == "python"
        assert chunk.file_path == "sample_project/auth.py"
        assert chunk.metadata["extension"] == ".py"
        assert "import hashlib" in chunk.metadata["imports"]
        assert "import os" in chunk.metadata["imports"]


def test_deterministic_id(parser, chunker, sample_dir):
    """Verify that running chunk creation twice produces identical deterministic IDs."""
    auth_file = sample_dir / "auth.py"
    parsed1 = parser.parse_file(auth_file)
    parsed2 = parser.parse_file(auth_file)

    chunks1 = chunker.chunk_parsed_file(parsed1, file_path_override="sample_project/auth.py")
    chunks2 = chunker.chunk_parsed_file(parsed2, file_path_override="sample_project/auth.py")

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.id == c2.id
        assert c1.symbol_name == c2.symbol_name
        assert c1.start_line == c2.start_line
        assert c1.end_line == c2.end_line


def test_json_serialization(parser, chunker, sample_dir):
    """Verify CodeChunk objects can be serialized to JSON and deserialized back."""
    utils_file = sample_dir / "utils.py"
    parsed = parser.parse_file(utils_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override="sample_project/utils.py")

    assert len(chunks) == 1
    chunk = chunks[0]

    chunk_dict = chunk.to_dict()
    json_str = json.dumps(chunk_dict)
    loaded_dict = json.loads(json_str)

    assert loaded_dict["id"] == chunk.id
    assert loaded_dict["file_path"] == "sample_project/utils.py"
    assert loaded_dict["language"] == "python"
    assert loaded_dict["symbol_name"] == "generate_uuid"
    assert loaded_dict["symbol_type"] == "function"
    assert loaded_dict["parent_symbol"] is None
    assert loaded_dict["start_line"] == 1
    assert loaded_dict["end_line"] == 3
    assert loaded_dict["metadata"]["extension"] == ".py"
    assert loaded_dict["metadata"]["imports"] == ["import uuid"]


def test_empty_file(parser, chunker, tmp_path: Path):
    """Verify that an empty Python file parses and chunks without crashing."""
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("")

    parsed = parser.parse_file(empty_file)
    chunks = chunker.chunk_parsed_file(parsed, file_path_override=str(empty_file))

    assert chunks == []


def test_syntax_error_file(parser, chunker, tmp_path: Path):
    """Verify that an invalid Python file is handled gracefully without crashing."""
    broken_file = tmp_path / "broken.py"
    broken_file.write_text("def broken_func(:\n    pass\n")

    parsed = parser.parse_file(broken_file)
    # Tree-sitter handles errors gracefully
    chunks = chunker.chunk_parsed_file(parsed, file_path_override=str(broken_file))
    assert isinstance(chunks, list)

    # Test parser error dict handling in chunker
    error_parsed = {"file": str(broken_file), "error": "Permission denied"}
    error_chunks = chunker.chunk_parsed_file(error_parsed)
    assert error_chunks == []
