import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.indexer.chunker import CodeChunk

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_BATCH_SIZE = 32


def build_embedding_text(chunk: CodeChunk) -> str:
    """
    Constructs a structured, deterministic semantic string representing the CodeChunk
    to provide rich contextual information to the embedding model.

    Example format:
        File: backend/users.py
        Language: python
        Type: method
        Class: User
        Symbol: save

        Code:
        def save(self):
            ...
    """
    parts = [
        f"File: {chunk.file_path}",
        f"Language: {chunk.language}",
        f"Type: {chunk.symbol_type}",
    ]
    if chunk.parent_symbol:
        parts.append(f"Class: {chunk.parent_symbol}")
    parts.append(f"Symbol: {chunk.symbol_name}")
    parts.append("")
    parts.append("Code:")
    parts.append(chunk.code)
    return "\n".join(parts)


class CodeEmbedder:
    """
    Manages local embedding model inference using sentence-transformers.
    Supports single text embedding, batch CodeChunk embedding, and vector dimension reporting.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        normalize_embeddings: bool = True,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings
        self.device = device
        self._model = None
        self._dimension: Optional[int] = None

    @property
    def model(self):
        """Lazily loads and returns the sentence-transformers model instance."""
        if self._model is None:
            self.load_model()
        return self._model

    def load_model(self) -> None:
        """Loads the embedding model into memory and caches its dimension."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. Please run 'pip install -r requirements.txt'"
            ) from e

        self._model = SentenceTransformer(self.model_name, device=self.device)
        if hasattr(self._model, "get_embedding_dimension"):
            self._dimension = int(self._model.get_embedding_dimension())
        else:
            self._dimension = int(self._model.get_sentence_embedding_dimension())

    @property
    def dimension(self) -> int:
        """Returns the numerical vector dimension of the loaded embedding model."""
        if self._dimension is None:
            _ = self.model  # Trigger lazy loading
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        """
        Generates an embedding vector for a single text string.

        Args:
            text: Query or code string to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty or whitespace-only text.")

        vec = self.model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return [float(x) for x in vec.tolist()]

    def embed_texts(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """
        Generates embedding vectors for a list of text strings in batches.

        Args:
            texts: List of strings to embed.
            batch_size: Optional batch size override.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        bs = batch_size if batch_size is not None else self.batch_size
        vecs = self.model.encode(
            texts,
            batch_size=bs,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return [[float(x) for x in v] for v in vecs.tolist()]

    def embed_chunks(
        self,
        chunks: List[CodeChunk],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """
        Constructs semantic embedding texts from CodeChunk objects and computes
        their vector embeddings in efficient batches.

        Args:
            chunks: List of CodeChunk objects.
            batch_size: Optional batch size override.

        Returns:
            List of embedding vectors matching the input chunk order.
        """
        if not chunks:
            return []

        texts = [build_embedding_text(c) for c in chunks]
        return self.embed_texts(texts, batch_size=batch_size)


def save_embedding_index(
    output_path: str | Path,
    model_name: str,
    dimension: int,
    chunks: List[CodeChunk],
    embeddings: List[List[float]],
) -> Path:
    """
    Saves generated chunk embeddings and associated metadata to a local JSON development index.

    Args:
        output_path: Path to the target json file (e.g. data/embeddings/index.json).
        model_name: Name/identifier of the embedding model.
        dimension: Embedding vector dimension.
        chunks: List of CodeChunk objects.
        embeddings: List of embedding vectors corresponding to chunks.

    Returns:
        Path to the saved index file.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    items = []
    for chunk, emb in zip(chunks, embeddings):
        items.append({
            "chunk_id": chunk.id,
            "file_path": chunk.file_path,
            "symbol_name": chunk.symbol_name,
            "symbol_type": chunk.symbol_type,
            "parent_symbol": chunk.parent_symbol,
            "embedding": emb,
        })

    index_data = {
        "model": model_name,
        "dimension": dimension,
        "total_chunks": len(items),
        "items": items,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)

    return out_file


def load_embedding_index(index_path: str | Path) -> dict:
    """
    Loads a previously saved local development embedding index.

    Args:
        index_path: Path to the index json file.

    Returns:
        Dictionary containing index metadata and items.
    """
    path = Path(index_path)
    if not path.is_file():
        raise FileNotFoundError(f"Embedding index not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
