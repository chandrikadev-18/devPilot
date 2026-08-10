from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode"
}

@dataclass
class FileInfo:
    """Metadata for a single file."""
    relative_path: str
    absolute_path: str
    file_name: str
    extension: str
    size_bytes: int

@dataclass
class ProjectStats:
    """Statistics for the scanned project."""
    total_files: int
    total_dirs: int
    extensions: Dict[str, int]

class ProjectScanner:
    """Recursively scans a directory and collects file information."""
    
    def __init__(self, ignored_dirs: Optional[set] = None):
        self.ignored_dirs = ignored_dirs if ignored_dirs is not None else set(IGNORED_DIRS)
    
    def scan(self, directory: str | Path) -> Tuple[List[FileInfo], ProjectStats]:
        """
        Scans the directory and returns a list of files and project statistics.
        """
        root_path = Path(directory).resolve()
        
        if not root_path.exists():
            raise FileNotFoundError(f"Directory does not exist: {root_path}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root_path}")

        files_info = []
        total_dirs = 0
        extensions_count = {}

        def _scan_dir(current_path: Path):
            nonlocal total_dirs
            try:
                for item in current_path.iterdir():
                    if item.is_dir():
                        if item.name not in self.ignored_dirs:
                            total_dirs += 1
                            _scan_dir(item)
                    elif item.is_file():
                        try:
                            size = item.stat().st_size
                            rel_path = item.relative_to(root_path)
                            ext = item.suffix.lower()
                            
                            info = FileInfo(
                                relative_path=str(rel_path),
                                absolute_path=str(item),
                                file_name=item.name,
                                extension=ext,
                                size_bytes=size
                            )
                            files_info.append(info)
                            extensions_count[ext] = extensions_count.get(ext, 0) + 1
                        except (PermissionError, FileNotFoundError):
                            # Skip files we cannot access
                            pass
            except PermissionError:
                # If we don't have permission to read a directory, skip it
                pass

        _scan_dir(root_path)
        
        stats = ProjectStats(
            total_files=len(files_info),
            total_dirs=total_dirs,
            extensions=extensions_count
        )
        
        return files_info, stats
