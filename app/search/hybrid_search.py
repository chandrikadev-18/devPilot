"""
DevPilot Hybrid & Semantic Code Search Engine.

Combines vector cosine similarity search with exact/fuzzy AST symbol matching,
deterministic re-ranking, and dependency graph relationship enrichment.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.indexer.chunker import CodeChunker
from app.parser.python_parser import PythonParser
from app.search.models import SemanticSearchOutput, SemanticSymbolResult
from app.search.semantic_search import SearchResult, SemanticSearcher
from app.vector_store.qdrant_store import ConfigurationMismatchError, ValidationError, VectorStoreError


def _extract_query_keywords(query: str) -> List[str]:
    """Extracts meaningful alphanumeric search tokens, discarding common stop words."""
    stop_words = {
        "where", "is", "are", "handled", "find", "code", "related", "to",
        "which", "responsible", "for", "the", "a", "an", "in", "of", "and",
        "do", "we", "handle", "show", "me", "how", "does", "get", "what",
        "implementation", "implemented", "part", "functionality", "validate",
        "validated", "connections", "connection",
    }
    raw_tokens = re.findall(r"[a-zA-Z0-9_]+", query.lower())
    meaningful = [t for t in raw_tokens if t not in stop_words and len(t) > 1]
    return meaningful if meaningful else raw_tokens


class HybridCodeSearchEngine:
    """
    Unified Semantic & Symbol Search Engine.
    Executes hybrid retrieval combining embeddings, AST parsing, and graph intelligence.
    """

    def __init__(
        self,
        searcher: Optional[SemanticSearcher] = None,
        project_root: Optional[Path] = None,
        graph: Optional[Any] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self._searcher = searcher
        self.graph = graph

    @property
    def searcher(self) -> Optional[SemanticSearcher]:
        if self._searcher is not None:
            return self._searcher
        try:
            self._searcher = SemanticSearcher()
            return self._searcher
        except Exception:
            return None

    def _get_active_graph(self) -> Optional[Any]:
        if self.graph is not None:
            return self.graph
        try:
            from app.agent.tools import _resolve_graph
            return _resolve_graph(None, self.project_root)
        except Exception:
            return None

    def _fallback_ast_scan(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Scans codebase Python files to extract symbols semantically matching query tokens
        when vector store is empty, unindexed, or unavailable.
        """
        keywords = _extract_query_keywords(query)
        parser = PythonParser()
        candidates: List[Dict[str, Any]] = []

        try:
            py_files = list(self.project_root.rglob("*.py"))
        except Exception:
            py_files = []

        for p in py_files:
            # Skip hidden and venv paths
            if any(part in {".venv", "venv", "env", ".git", "__pycache__"} for part in p.parts):
                continue

            rel_path = p.relative_to(self.project_root).as_posix()
            try:
                parsed = parser.parse_file(p)
            except Exception:
                continue

            if not parsed or "error" in parsed:
                continue

            # Check classes
            for cls in parsed.get("classes", []):
                name = cls.get("name", "")
                source = cls.get("source", "")
                score = self._compute_token_match_score(name, rel_path, source, keywords)
                if score > 0.2:
                    candidates.append({
                        "symbol": name,
                        "file": rel_path,
                        "symbol_type": "class",
                        "parent_symbol": None,
                        "start_line": cls.get("start_line", 1),
                        "end_line": cls.get("end_line", 1),
                        "score": score,
                        "code": source[:400],
                    })

            # Check functions
            for fn in parsed.get("functions", []):
                name = fn.get("name", "")
                source = fn.get("source", "")
                score = self._compute_token_match_score(name, rel_path, source, keywords)
                if score > 0.2:
                    candidates.append({
                        "symbol": name,
                        "file": rel_path,
                        "symbol_type": "function",
                        "parent_symbol": None,
                        "start_line": fn.get("start_line", 1),
                        "end_line": fn.get("end_line", 1),
                        "score": score,
                        "code": source[:400],
                    })

            # Check methods
            for m in parsed.get("methods", []):
                name = m.get("name", "")
                parent = m.get("parent_class", "")
                full_name = f"{parent}.{name}" if parent else name
                source = m.get("source", "")
                score = self._compute_token_match_score(full_name, rel_path, source, keywords)
                if score > 0.2:
                    candidates.append({
                        "symbol": full_name,
                        "file": rel_path,
                        "symbol_type": "method",
                        "parent_symbol": parent,
                        "start_line": m.get("start_line", 1),
                        "end_line": m.get("end_line", 1),
                        "score": score,
                        "code": source[:400],
                    })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]

    def _compute_token_match_score(
        self, symbol_name: str, file_path: str, source: str, keywords: List[str]
    ) -> float:
        """Computes a heuristic relevance score [0.0, 1.0] based on token overlap."""
        if not keywords:
            return 0.3

        sym_lower = symbol_name.lower()
        file_lower = file_path.lower()
        src_lower = source[:500].lower()

        score = 0.40  # base
        matches = 0

        for kw in keywords:
            kw_stem = kw.rstrip("sed")
            if kw in sym_lower or (len(kw_stem) >= 3 and kw_stem in sym_lower):
                score += 0.25
                matches += 1
            elif kw in file_lower or (len(kw_stem) >= 3 and kw_stem in file_lower):
                score += 0.15
                matches += 1
            elif kw in src_lower:
                score += 0.08
                matches += 1

        if matches == 0:
            return 0.0

        return min(0.95, score)

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> SemanticSearchOutput:
        """
        Performs hybrid semantic search for the given query and enriches results with graph context.
        """
        if not query or not query.strip():
            raise ValidationError("Search query cannot be empty.")

        if not isinstance(top_k, int) or top_k <= 0:
            raise ValidationError(f"top_k must be a positive integer, got {top_k}.")

        q_clean = query.strip()
        keywords = _extract_query_keywords(q_clean)

        # 1. Attempt Vector Store Semantic Search
        vector_results: List[SearchResult] = []
        try:
            s = self.searcher
            if s is not None:
                vector_results = s.search(
                    query=q_clean,
                    top_k=max(top_k * 2, 10),
                    min_score=min_score,
                )
        except Exception:
            vector_results = []

        # 2. Collect candidates (combining Vector results & AST Symbol fallback)
        candidate_items: Dict[str, Dict[str, Any]] = {}

        for vr in vector_results:
            sym_name = f"{vr.parent_symbol}.{vr.symbol_name}" if vr.parent_symbol else vr.symbol_name
            k = f"{vr.file_path}:{sym_name}"
            # Normalize vector score (cosine similarity usually in 0.5 - 1.0 range)
            norm_score = max(0.0, min(1.0, float(vr.score)))
            candidate_items[k] = {
                "symbol": sym_name,
                "file": vr.file_path,
                "symbol_type": vr.symbol_type or "function",
                "parent_symbol": vr.parent_symbol,
                "start_line": vr.start_line,
                "end_line": vr.end_line,
                "score": norm_score,
                "code": vr.code,
            }

        # If vector results are few or empty, supplement with AST scan
        if len(candidate_items) < top_k:
            ast_candidates = self._fallback_ast_scan(q_clean, top_k=top_k * 2)
            for ac in ast_candidates:
                k = f"{ac['file']}:{ac['symbol']}"
                if k not in candidate_items:
                    candidate_items[k] = ac

        # 3. Deterministic Re-ranking
        ranked_list: List[Dict[str, Any]] = []
        active_graph = self._get_active_graph()

        for k, c in candidate_items.items():
            sym = c["symbol"]
            file_p = c["file"]
            raw_score = c["score"]

            # Compute boosts
            exact_sym_boost = 0.0
            file_boost = 0.0
            graph_boost = 0.0

            sym_lower = sym.lower()
            file_lower = file_p.lower()

            for kw in keywords:
                if kw in sym_lower:
                    exact_sym_boost = max(exact_sym_boost, 0.15)
                if kw in file_lower:
                    file_boost = max(file_boost, 0.10)

            # Check graph connectivity
            if active_graph:
                try:
                    nodes = active_graph.find_nodes_by_name(sym.split(".")[-1])
                    if nodes:
                        graph_boost = 0.05
                except Exception:
                    pass

            final_score = min(1.0, max(0.0, raw_score + exact_sym_boost + file_boost + graph_boost))
            c["final_score"] = final_score
            ranked_list.append(c)

        ranked_list.sort(key=lambda item: item["final_score"], reverse=True)

        # 4. Dependency Graph Context Enrichment for top results
        final_results: List[SemanticSymbolResult] = []
        seen_keys: Set[str] = set()

        for item in ranked_list:
            sym_full = item["symbol"]
            file_p = item["file"]
            k = f"{file_p}:{sym_full}"
            if k in seen_keys:
                continue
            seen_keys.add(k)

            related: List[str] = []
            base_sym_name = sym_full.split(".")[-1]

            if active_graph:
                try:
                    from app.graph.queries import get_callees, get_callers
                    callees = get_callees(active_graph, symbol=sym_full)
                    for cal in callees[:4]:
                        related.append(cal["name"])
                    callers = get_callers(active_graph, symbol=sym_full)
                    for car in callers[:3]:
                        if car["name"] not in related:
                            related.append(car["name"])
                except Exception:
                    pass

            # Generate descriptive reason
            if related:
                reason = f"Implements core functionality for {keywords[0] if keywords else 'query'}; connected to {', '.join(related[:3])}"
            else:
                reason = f"Primary implementation related to {', '.join(keywords[:2]) if keywords else 'query'}"

            final_results.append(
                SemanticSymbolResult(
                    symbol=sym_full,
                    file=file_p,
                    start_line=item.get("start_line", 1),
                    end_line=item.get("end_line", 1),
                    score=item["final_score"],
                    reason=reason,
                    symbol_type=item.get("symbol_type", "function"),
                    parent_symbol=item.get("parent_symbol"),
                    related_symbols=related,
                    code_snippet=item.get("code"),
                )
            )

            if len(final_results) >= top_k:
                break

        return SemanticSearchOutput(
            query=q_clean,
            results=final_results,
        )
