from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_client.models import FieldCondition, Filter, MatchText, MatchValue

from app.embeddings.embedder import CodeEmbedder
from app.vector_store.qdrant_store import (
    DEFAULT_COLLECTION_NAME,
    ConfigurationMismatchError,
    QdrantVectorStore,
    ValidationError,
    VectorStoreError,
)


@dataclass
class SearchResult:
    """
    Application-level representation of a retrieved code chunk matching a search query.
    """
    chunk_id: str
    score: float
    file_path: str
    symbol_name: str
    symbol_type: str
    parent_symbol: Optional[str]
    start_line: int
    end_line: int
    code: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the SearchResult instance into a serializable dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "score": round(self.score, 4),
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type,
            "parent_symbol": self.parent_symbol,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "code": self.code,
            "metadata": self.metadata,
        }


class SemanticSearcher:
    """
    Executes semantic code search by converting natural language queries into
    embedding vectors and performing cosine similarity searches across stored code chunks in Qdrant.
    """

    def __init__(
        self,
        embedder: Optional[CodeEmbedder] = None,
        vector_store: Optional[QdrantVectorStore] = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ):
        self.embedder = embedder if embedder is not None else CodeEmbedder()
        self.vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self.collection_name = collection_name

    def verify_collection_compatibility(self) -> None:
        """
        Verifies that the target Qdrant collection exists, contains indexed vectors,
        and its dimensions are compatible with the current embedding model.

        Raises:
            VectorStoreError: If collection is missing or empty.
            ConfigurationMismatchError: If vector dimensions differ.
        """
        if not self.vector_store.collection_exists(self.collection_name):
            raise VectorStoreError(
                f"No indexed code found.\nRun:\n  python -m app.main store .\nfirst."
            )

        info = self.vector_store.get_collection_info(self.collection_name)
        points_count = info.get("points", 0)
        if points_count == 0:
            raise VectorStoreError(
                f"No indexed code found in collection '{self.collection_name}'.\nRun:\n  python -m app.main store .\nfirst."
            )

        col_dim = info.get("vector_size")
        model_dim = self.embedder.dimension
        if col_dim is not None and col_dim != model_dim:
            raise ConfigurationMismatchError(
                f"Embedding configuration mismatch.\n\n"
                f"Current model dimension:\n{model_dim}\n\n"
                f"Qdrant collection dimension:\n{col_dim}\n\n"
                f"Recreate/reindex the collection with the correct embedding model."
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
        extension: Optional[str] = None,
        path_prefix: Optional[str] = None,
        symbol_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Executes semantic search for the given query.

        Args:
            query: Natural language query string.
            top_k: Maximum number of ranked results to return.
            min_score: Optional minimum cosine similarity threshold.
            extension: Optional file extension filter (e.g. '.py').
            path_prefix: Optional path prefix filter (e.g. 'backend/').
            symbol_type: Optional symbol type filter ('function', 'class', 'method').

        Returns:
            List of SearchResult objects sorted by descending similarity score.
        """
        if not query or not query.strip():
            raise ValidationError("Search query cannot be empty.")

        if not isinstance(top_k, int) or top_k <= 0:
            raise ValidationError(f"top_k must be a positive integer, got {top_k}.")

        if min_score is not None and (not isinstance(min_score, (int, float)) or min_score < -1.0 or min_score > 1.0):
            raise ValidationError(f"min_score must be a float between -1.0 and 1.0, got {min_score}.")

        self.verify_collection_compatibility()

        # Generate query vector
        query_vector = self.embedder.embed_text(query)

        # Build Qdrant filter conditions where applicable
        conditions = []
        if symbol_type:
            conditions.append(FieldCondition(key="symbol_type", match=MatchValue(value=symbol_type.strip().lower())))
        if extension:
            ext = extension.strip().lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            conditions.append(FieldCondition(key="metadata.extension", match=MatchValue(value=ext)))
        if path_prefix:
            normalized_prefix = Path(path_prefix.strip()).as_posix()
            conditions.append(FieldCondition(key="file_path", match=MatchText(text=normalized_prefix)))

        qdrant_filter = Filter(must=conditions) if conditions else None

        # Fetch extra candidate points to ensure top_k is met after deduplication / post-filtering
        search_limit = max(top_k * 3, top_k + 20)
        scored_points = self.vector_store.search(
            query_vector=query_vector,
            collection_name=self.collection_name,
            limit=search_limit,
            score_threshold=min_score,
            query_filter=qdrant_filter,
        )

        results: List[SearchResult] = []
        seen_chunk_ids = set()

        for pt in scored_points:
            payload = pt.payload or {}
            chunk_id = payload.get("chunk_id") or str(pt.id)
            if chunk_id in seen_chunk_ids:
                continue

            file_path = payload.get("file_path", "")
            # Precise path filter validation
            if path_prefix:
                norm_fp = Path(file_path).as_posix().lower()
                norm_prefix = Path(path_prefix.strip()).as_posix().lower()
                if not norm_fp.startswith(norm_prefix) and norm_prefix not in norm_fp:
                    continue

            # Precise extension filter validation
            if extension:
                ext = extension.strip().lower()
                if not ext.startswith("."):
                    ext = f".{ext}"
                if not file_path.lower().endswith(ext):
                    continue

            # Precise symbol_type filter validation
            if symbol_type:
                st = payload.get("symbol_type", "").lower()
                if st != symbol_type.strip().lower():
                    continue

            seen_chunk_ids.add(chunk_id)
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    score=float(pt.score),
                    file_path=file_path,
                    symbol_name=payload.get("symbol_name", ""),
                    symbol_type=payload.get("symbol_type", ""),
                    parent_symbol=payload.get("parent_symbol"),
                    start_line=payload.get("start_line", 0),
                    end_line=payload.get("end_line", 0),
                    code=payload.get("code", ""),
                    metadata=payload.get("metadata", {}),
                )
            )

            if len(results) >= top_k:
                break

        # Ensure sorted descending by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results
