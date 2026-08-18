"""
RAG Context Builder.

Transforms retrieved SearchResult objects into clean, bounded,
and structured context suitable for LLM prompts with source metadata preservation.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.config import get_max_context_characters, get_max_context_chunks
from app.search.semantic_search import SearchResult


@dataclass
class SourceCitation:
    """Structured representation of a source code reference used in RAG answers."""
    chunk_id: str
    file_path: str
    symbol_name: str
    symbol_type: str
    parent_symbol: Optional[str]
    start_line: int
    end_line: int
    score: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes citation to a clean dictionary."""
        d = {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": round(self.score, 4),
        }
        if self.parent_symbol:
            d["parent_symbol"] = self.parent_symbol
        return d


class ContextBuilder:
    """
    Constructs bounded prompt context from retrieved SearchResult instances.
    Enforces maximum chunk counts and character safety limits.
    """

    def __init__(
        self,
        max_chunks: Optional[int] = None,
        max_characters: Optional[int] = None,
    ):
        self.max_chunks = max_chunks if max_chunks is not None else get_max_context_chunks()
        self.max_characters = max_characters if max_characters is not None else get_max_context_characters()

    def build_context(
        self,
        search_results: List[SearchResult],
    ) -> Tuple[str, List[SourceCitation]]:
        """
        Formats search results into structured LLM context and extracts citation records.

        Args:
            search_results: List of retrieved SearchResult objects, ordered by relevance.

        Returns:
            Tuple of (formatted_context_string, list_of_source_citations).
        """
        if not search_results:
            return "", []

        # Enforce max chunks limit (preserving most relevant first)
        selected_results = search_results[: self.max_chunks]

        context_blocks: List[str] = []
        citations: List[SourceCitation] = []
        current_length = 0
        truncated = False

        for idx, result in enumerate(selected_results, start=1):
            citation = SourceCitation(
                chunk_id=result.chunk_id,
                file_path=result.file_path,
                symbol_name=result.symbol_name,
                symbol_type=result.symbol_type,
                parent_symbol=result.parent_symbol,
                start_line=result.start_line,
                end_line=result.end_line,
                score=result.score,
            )

            # Build source block
            lines = [f"--- SOURCE {idx} ---"]
            lines.append(f"File: {result.file_path}")
            lines.append(f"Symbol: {result.symbol_name}")
            lines.append(f"Type: {result.symbol_type}")
            if result.parent_symbol:
                lines.append(f"Class: {result.parent_symbol}")
            lines.append(f"Lines: {result.start_line}-{result.end_line}")
            lines.append(f"Score: {result.score:.4f}")
            lines.append("")
            lines.append("Code:")
            lines.append(result.code.strip())
            lines.append("")

            block_text = "\n".join(lines)
            block_length = len(block_text)

            # Check character limit
            if current_length + block_length > self.max_characters:
                # If we have capacity for a partial block, truncate it safely
                available = self.max_characters - current_length
                if available > 200:
                    truncated_block = block_text[:available].rstrip() + "\n\n[Code snippet truncated due to character limit]"
                    context_blocks.append(truncated_block)
                    citations.append(citation)
                truncated = True
                break

            context_blocks.append(block_text)
            citations.append(citation)
            current_length += block_length

        if truncated and not context_blocks:
            # Handle extreme edge case where even first block is too large
            first_res = selected_results[0]
            context_blocks.append(
                f"--- SOURCE 1 ---\nFile: {first_res.file_path}\nSymbol: {first_res.symbol_name}\n"
                f"Lines: {first_res.start_line}-{first_res.end_line}\n\nCode:\n"
                f"{first_res.code[:self.max_characters - 100].strip()}\n\n[Context truncated due to size limit]"
            )
            citations.append(
                SourceCitation(
                    chunk_id=first_res.chunk_id,
                    file_path=first_res.file_path,
                    symbol_name=first_res.symbol_name,
                    symbol_type=first_res.symbol_type,
                    parent_symbol=first_res.parent_symbol,
                    start_line=first_res.start_line,
                    end_line=first_res.end_line,
                    score=first_res.score,
                )
            )

        context_str = "\n".join(context_blocks).strip()
        return context_str, citations
