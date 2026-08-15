import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List


@dataclass
class CodeChunk:
    """
    Data model representing an isolated, semantically meaningful code chunk
    (function, class, or method) extracted from source files.
    """
    id: str
    file_path: str
    language: str
    symbol_name: str
    symbol_type: str
    parent_symbol: Optional[str]
    start_line: int
    end_line: int
    code: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the CodeChunk instance into a serializable dictionary."""
        return asdict(self)


def generate_chunk_id(
    file_path: str,
    symbol_type: str,
    symbol_name: str,
    start_line: int,
    end_line: int,
    parent_symbol: Optional[str] = None,
) -> str:
    """
    Generates a deterministic SHA-256 hash ID for a code chunk.

    The hash is computed over a normalized, colon-separated string:
        normalized_path:symbol_type:parent_symbol:symbol_name:start_line:end_line
    """
    # Normalize file path using POSIX forward slashes for cross-platform stability
    normalized_path = Path(file_path).as_posix() if file_path else ""
    parent = parent_symbol if parent_symbol is not None else ""
    raw_key = f"{normalized_path}:{symbol_type}:{parent}:{symbol_name}:{start_line}:{end_line}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class CodeChunker:
    """
    Converts structured AST symbols extracted by the parser into
    standardized, reusable CodeChunk objects with associated metadata.
    """

    def __init__(self, default_language: str = "python"):
        self.default_language = default_language

    def chunk_parsed_file(
        self, parsed_file: dict, file_path_override: Optional[str] = None
    ) -> List[CodeChunk]:
        """
        Converts the symbols in a single parsed file output into a list of CodeChunks.

        Args:
            parsed_file: Dictionary containing parsed AST data from PythonParser.
            file_path_override: Optional custom path (e.g. relative path) to use in chunks.

        Returns:
            List of CodeChunk instances.
        """
        if not parsed_file or "error" in parsed_file:
            return []

        raw_file_path = parsed_file.get("file", "")
        file_path = file_path_override if file_path_override is not None else raw_file_path
        file_ext = Path(file_path).suffix.lower() if file_path else ".py"

        # Extract file-level imports for metadata
        raw_imports = parsed_file.get("imports", [])
        import_sources: List[str] = []
        for imp in raw_imports:
            if isinstance(imp, dict) and "source" in imp:
                import_sources.append(imp["source"])
            elif isinstance(imp, str):
                import_sources.append(imp)

        base_metadata: Dict[str, Any] = {
            "extension": file_ext,
            "imports": import_sources,
        }

        chunks: List[CodeChunk] = []

        # 1. Process Class definitions
        for cls_item in parsed_file.get("classes", []):
            name = cls_item.get("name", "")
            start_line = cls_item.get("start_line", 0)
            end_line = cls_item.get("end_line", 0)
            code = cls_item.get("source", "")
            chunk_id = generate_chunk_id(
                file_path=file_path,
                symbol_type="class",
                symbol_name=name,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=None,
            )
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=file_path,
                    language=self.default_language,
                    symbol_name=name,
                    symbol_type="class",
                    parent_symbol=None,
                    start_line=start_line,
                    end_line=end_line,
                    code=code,
                    metadata=dict(base_metadata),
                )
            )

        # 2. Process standalone Function definitions
        for fn_item in parsed_file.get("functions", []):
            name = fn_item.get("name", "")
            start_line = fn_item.get("start_line", 0)
            end_line = fn_item.get("end_line", 0)
            code = fn_item.get("source", "")
            chunk_id = generate_chunk_id(
                file_path=file_path,
                symbol_type="function",
                symbol_name=name,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=None,
            )
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=file_path,
                    language=self.default_language,
                    symbol_name=name,
                    symbol_type="function",
                    parent_symbol=None,
                    start_line=start_line,
                    end_line=end_line,
                    code=code,
                    metadata=dict(base_metadata),
                )
            )

        # 3. Process Method definitions (functions inside a class)
        for m_item in parsed_file.get("methods", []):
            name = m_item.get("name", "")
            parent_class = m_item.get("parent_class")
            start_line = m_item.get("start_line", 0)
            end_line = m_item.get("end_line", 0)
            code = m_item.get("source", "")
            chunk_id = generate_chunk_id(
                file_path=file_path,
                symbol_type="method",
                symbol_name=name,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_class,
            )
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=file_path,
                    language=self.default_language,
                    symbol_name=name,
                    symbol_type="method",
                    parent_symbol=parent_class,
                    start_line=start_line,
                    end_line=end_line,
                    code=code,
                    metadata=dict(base_metadata),
                )
            )

        # Order chunks naturally by line number
        chunks.sort(key=lambda c: (c.start_line, c.end_line))
        return chunks
