"""DevPilot Embeddings module for local vector embeddings."""

from app.embeddings.embedder import (
    CodeEmbedder,
    build_embedding_text,
    save_embedding_index,
    load_embedding_index,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_BATCH_SIZE,
)

__all__ = [
    "CodeEmbedder",
    "build_embedding_text",
    "save_embedding_index",
    "load_embedding_index",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_BATCH_SIZE",
]
