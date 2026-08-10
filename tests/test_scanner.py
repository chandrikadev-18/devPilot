import pytest
from pathlib import Path
from app.scanner.scanner import ProjectScanner, FileInfo, ProjectStats

@pytest.fixture
def sample_project(tmp_path: Path):
    """Creates a dummy project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.js").write_text("console.log('hello')")
    
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Docs")
    
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.json").write_text("{}")
    
    (tmp_path / "README.md").write_text("# Readme")
    
    return tmp_path

def test_scan_directory(sample_project: Path):
    """Tests basic scanning and counting of files/dirs."""
    scanner = ProjectScanner()
    files, stats = scanner.scan(sample_project)
    
    # .git and node_modules should be ignored
    assert stats.total_files == 4  # main.py, utils.js, index.md, README.md
    assert stats.total_dirs == 2   # src, docs

def test_ignored_directories(sample_project: Path):
    """Tests that ignored directories are skipped."""
    scanner = ProjectScanner()
    files, stats = scanner.scan(sample_project)
    
    for file in files:
        assert ".git" not in file.absolute_path
        assert "node_modules" not in file.absolute_path

def test_file_metadata(sample_project: Path):
    """Tests that file metadata is collected correctly."""
    scanner = ProjectScanner()
    files, stats = scanner.scan(sample_project)
    
    main_py_info = next((f for f in files if f.file_name == "main.py"), None)
    assert main_py_info is not None
    assert main_py_info.extension == ".py"
    assert "src" in main_py_info.relative_path
    assert main_py_info.size_bytes > 0

def test_extension_statistics(sample_project: Path):
    """Tests that extension counts are computed correctly."""
    scanner = ProjectScanner()
    files, stats = scanner.scan(sample_project)
    
    assert stats.extensions.get(".py") == 1
    assert stats.extensions.get(".js") == 1
    assert stats.extensions.get(".md") == 2
    assert ".json" not in stats.extensions  # inside node_modules

def test_invalid_directory():
    """Tests behavior when scanning non-existent directory."""
    scanner = ProjectScanner()
    with pytest.raises(FileNotFoundError):
        scanner.scan("non_existent_directory_123")

def test_not_a_directory(tmp_path: Path):
    """Tests behavior when passing a file path instead of a directory."""
    scanner = ProjectScanner()
    file_path = tmp_path / "test.txt"
    file_path.write_text("test")
    
    with pytest.raises(NotADirectoryError):
        scanner.scan(file_path)
