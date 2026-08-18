"""
RAG Codebase Question Answering Pipeline.

Orchestrates semantic search retrieval, context construction, prompt generation,
and LLM generation into a cohesive, grounded codebase Q&A workflow.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.llm.base import LLMProvider
from app.rag.context_builder import ContextBuilder, SourceCitation
from app.search.semantic_search import SearchResult, SemanticSearcher

DEFAULT_SYSTEM_PROMPT = """You are DevPilot, a codebase analysis assistant.

Answer the user's question using ONLY the supplied code context.

Rules:
1. Do not invent code or files.
2. If the context is insufficient, explicitly say that.
3. Explain the relevant implementation clearly.
4. Mention source files and symbols.
5. Use line ranges when available.
6. Keep the answer focused on the question.
"""

NO_RELEVANT_CONTEXT_ANSWER = (
    "I couldn't find enough relevant code in the indexed project to answer this question confidently.\n\n"
    "Suggested action:\n"
    "Run the indexing command again if the project has changed."
)


@dataclass
class QAResult:
    """
    Structured representation of a completed Question Answering result.
    """
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    search_results: List[SearchResult] = field(default_factory=list)
    context_used: str = ""
    provider: str = ""
    model: str = ""
    timings: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts QAResult into a clean JSON-serializable dictionary."""
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            "provider": self.provider,
            "model": self.model,
            "timings": {k: round(v, 4) for k, v in self.timings.items()},
        }


class RAGPipeline:
    """
    Retrieval-Augmented Generation Pipeline for Codebase Question Answering.
    """

    def __init__(
        self,
        searcher: SemanticSearcher,
        llm: LLMProvider,
        context_builder: Optional[ContextBuilder] = None,
        system_prompt: Optional[str] = None,
    ):
        self.searcher = searcher
        self.llm = llm
        self.context_builder = context_builder if context_builder is not None else ContextBuilder()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def build_user_prompt(self, question: str, context: str) -> str:
        """Constructs deterministic user prompt combining question and code context."""
        return (
            f"User Question:\n"
            f"{question.strip()}\n\n"
            f"Code Context:\n"
            f"{context.strip()}\n\n"
            f"Answer:\n"
        )

    def ask(
        self,
        question: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
        extension: Optional[str] = None,
        path_prefix: Optional[str] = None,
        symbol_type: Optional[str] = None,
    ) -> QAResult:
        """
        Executes grounded Q&A over the codebase.

        Args:
            question: User question string.
            top_k: Maximum number of search results to retrieve.
            min_score: Optional minimum similarity threshold.
            extension: Optional file extension filter.
            path_prefix: Optional file path prefix filter.
            symbol_type: Optional symbol type filter.

        Returns:
            QAResult containing answer, sources, and timing metrics.
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        t_start = time.time()

        # Step 1: Semantic Search Retrieval
        t_search_start = time.time()
        search_results = self.searcher.search(
            query=question,
            top_k=top_k,
            min_score=min_score,
            extension=extension,
            path_prefix=path_prefix,
            symbol_type=symbol_type,
        )
        t_search_end = time.time()
        search_time = t_search_end - t_search_start

        # Step 2: Handle no relevant results (avoid empty context LLM call)
        if not search_results:
            total_time = time.time() - t_start
            return QAResult(
                question=question.strip(),
                answer=NO_RELEVANT_CONTEXT_ANSWER,
                sources=[],
                search_results=[],
                context_used="",
                provider=self.llm.provider_name,
                model=self.llm.model_name,
                timings={
                    "search": search_time,
                    "llm": 0.0,
                    "total": total_time,
                },
            )

        # Step 3: Build structured LLM Context
        t_ctx_start = time.time()
        context_str, citations = self.context_builder.build_context(search_results)
        t_ctx_end = time.time()
        ctx_time = t_ctx_end - t_ctx_start

        # Step 4: Build deterministic prompt
        user_prompt = self.build_user_prompt(question=question, context=context_str)

        # Step 5: LLM Generation
        t_llm_start = time.time()
        answer = self.llm.generate(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
        )
        t_llm_end = time.time()
        llm_time = t_llm_end - t_llm_start

        total_time = time.time() - t_start

        return QAResult(
            question=question.strip(),
            answer=answer,
            sources=[c.to_dict() for c in citations],
            search_results=search_results,
            context_used=context_str,
            provider=self.llm.provider_name,
            model=self.llm.model_name,
            timings={
                "search": search_time,
                "context": ctx_time,
                "llm": llm_time,
                "total": total_time,
            },
        )
