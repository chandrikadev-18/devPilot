"""
DevPilot RAG Module.

Exposes ContextBuilder, SourceCitation, RAGPipeline, and QAResult.
"""

from app.rag.context_builder import ContextBuilder, SourceCitation
from app.rag.qa import (
    DEFAULT_SYSTEM_PROMPT,
    NO_RELEVANT_CONTEXT_ANSWER,
    QAResult,
    RAGPipeline,
)

__all__ = [
    "ContextBuilder",
    "SourceCitation",
    "RAGPipeline",
    "QAResult",
    "DEFAULT_SYSTEM_PROMPT",
    "NO_RELEVANT_CONTEXT_ANSWER",
]
