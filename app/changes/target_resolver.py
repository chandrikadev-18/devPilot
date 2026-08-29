"""
DevPilot Target Resolution & Symbol Disambiguation Engine (v1.9.1).

Implements grounded symbol and target resolution across dependency graphs, AST,
and semantic search with strict 5-tier priority:
1. Exact qualified symbol (e.g. GraphBuilder.build, AuthService.verify_password)
2. Exact symbol + file/class context (e.g. app/graph/builder.py:build)
3. Exact unqualified symbol (e.g. ASTExtractor if unique; flags ambiguous otherwise)
4. Semantic search (natural language concept fallback)
5. Ambiguous / Unresolved (structured ambiguity without unsafe guessing)
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.intent import QuestionIntent, classify_question_intent
from app.graph.models import NodeType
from app.graph.store import GraphStore
from app.parser.python_parser import PythonParser


IGNORED_EXTENSIONS = {
    ".py", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg",
    ".ini", ".env", ".sh", ".bat", ".lock", ".rst", ".html", ".css",
    ".js", ".ts", ".png", ".jpg", ".svg", ".log", ".csv",
}


def _clean_token(raw: str) -> str:
    """Cleans punctuation and common natural language wrappers from a token."""
    cleaned = raw.strip().strip("'\"`?,.:;()[]{}")
    prefixes = [
        "improve ", "optimize ", "refactor ", "update ", "modify ", "fix ",
        "change ", "rewrite ", "enhance ", "add feature to ", "performance of ",
        "in ", "for ", "the ", "function ", "class ", "method ", "module ",
        "what would be affected if ", "what could be affected if ", "what breaks if ",
        "what changes if ", "explain what would be affected if ", "explain the impact of ",
        "explain what breaks if ", "explain ", "what does ", "what do ", "where is ",
        "where do we ", "where are ", "find ", "show ", "who calls ", "who wrote ",
        "why was ", "impact of ", "dependencies of ", "dependents of ",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True

    suffixes = [
        " performance", " speed", " logic", " implementation", " function",
        " method", " class", " module", " behavior", " bug", " feature",
        " changes", " breaks", " is modified", " is updated", " is changed",
        " depend on", " depends on", " handled", " defined",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if cleaned.lower().endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
                changed = True

    return cleaned.strip().strip("'\"`?,.:;()[]{}")


@dataclass
class ResolvedTarget:
    """Represents the structured result of target resolution."""
    target: str
    target_symbol: str = ""
    target_file: str = ""
    target_lines: Optional[str] = None
    resolution_method: str = "unresolved"  # exact_qualified, symbol_with_context, exact_unqualified, semantic_search, ambiguous, unresolved
    confidence: float = 0.0
    is_ambiguous: bool = False
    ambiguity_candidates: List[Dict[str, Any]] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)
    raw_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "target_lines": self.target_lines,
            "resolution_method": self.resolution_method,
            "confidence": self.confidence,
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_candidates": self.ambiguity_candidates,
            "unverified": self.unverified,
        }


class TargetResolver:
    """
    Resolves natural language queries and developer change requests to exact AST / Graph targets
    with deterministic 5-tier priority, preventing semantic search from overriding exact symbols.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def resolve(
        self,
        request: str,
        graph: Optional[GraphStore] = None,
    ) -> ResolvedTarget:
        """
        Resolves a change request or question to an exact target symbol, file, and line span.
        """
        if not request or not request.strip():
            return ResolvedTarget(
                target="Unknown",
                resolution_method="unresolved",
                confidence=0.0,
                unverified=["Request cannot be empty."],
                raw_query=request or "",
            )

        q_clean = request.strip()

        # 0. Resolve active graph if available
        active_graph = graph
        if active_graph is None:
            try:
                from app.agent.tools import _resolve_graph
                active_graph = _resolve_graph(None, self.project_root)
            except Exception:
                active_graph = None

        # 0b. Extract candidates from query
        intent_info = classify_question_intent(q_clean)
        
        # 1. Check for explicit qualified symbols (e.g. GraphBuilder.build, AuthService.verify_password)
        # Priority 1: Exact qualified symbol
        res_p1 = self._resolve_exact_qualified(q_clean, intent_info.target_symbol, active_graph)
        if res_p1 is not None:
            return res_p1

        # 2. Check for explicit file / symbol context (e.g. app/graph/builder.py:build or app/graph/builder.py)
        # Priority 2: Exact symbol + file/class context
        res_p2 = self._resolve_symbol_with_context(q_clean, intent_info.target_symbol, active_graph)
        if res_p2 is not None:
            return res_p2

        # 3. Check for unqualified symbol (e.g. ASTExtractor, build_chunk_payload, build)
        # Priority 3: Exact unqualified symbol (only skipped for conceptual SEMANTIC_SEARCH queries)
        if intent_info.intent != QuestionIntent.SEMANTIC_SEARCH:
            res_p3 = self._resolve_exact_unqualified(q_clean, intent_info.target_symbol, active_graph)
            if res_p3 is not None:
                return res_p3

        # 4. Semantic Search fallback
        # Priority 4: Semantic search
        res_p4 = self._resolve_semantic_search(q_clean, intent_info.target_symbol, active_graph)
        if res_p4 is not None:
            return res_p4

        # 5. Ambiguous / Unresolved fallback
        # Priority 5: Ambiguous / Unresolved
        cand = intent_info.target_symbol or _clean_token(q_clean) or q_clean
        return ResolvedTarget(
            target=cand,
            target_symbol=cand,
            target_file="",
            target_lines=None,
            resolution_method="unresolved",
            confidence=0.0,
            is_ambiguous=False,
            unverified=[f"Target '{cand}' could not be verified in the codebase."],
            raw_query=q_clean,
        )

    # ==========================================================================
    # Priority 1: Exact Qualified Symbol
    # ==========================================================================

    def _resolve_exact_qualified(
        self,
        request: str,
        intent_target: Optional[str],
        graph: Optional[GraphStore],
    ) -> Optional[ResolvedTarget]:
        """Resolves exact qualified symbols (Class.method or module.Symbol)."""
        qualified_candidates: List[str] = []

        # Check intent target
        if intent_target and "." in intent_target:
            ext = Path(intent_target).suffix.lower()
            if ext not in IGNORED_EXTENSIONS:
                qualified_candidates.append(intent_target)

        # Regex extract Class.method tokens (e.g. GraphBuilder.build, AuthService.verify_password)
        # Matches Parent.Child or Class.method
        tokens = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b", request)
        for t in tokens:
            ext = Path(t).suffix.lower()
            if ext not in IGNORED_EXTENSIONS and t not in qualified_candidates:
                qualified_candidates.append(t)

        # Also check backticks
        bt_matches = re.findall(r"`([^`]+)`", request)
        for bt in bt_matches:
            if "." in bt:
                ext = Path(bt).suffix.lower()
                if ext not in IGNORED_EXTENSIONS and bt not in qualified_candidates:
                    qualified_candidates.append(bt)

        for cand in qualified_candidates:
            parts = cand.split(".")
            parent_name = parts[-2]
            member_name = parts[-1]

            # 1. Search in GraphStore
            matched_nodes = []
            if graph:
                from app.graph.queries import _resolve_target_nodes
                try:
                    matched_nodes = _resolve_target_nodes(graph, cand, allow_multiple=True)
                except Exception:
                    matched_nodes = []

                if not matched_nodes:
                    # Search by member name and filter parent_class
                    nodes = graph.find_nodes_by_name(member_name)
                    for n in nodes:
                        p_cls = n.metadata.get("parent_class") or ""
                        if p_cls.lower() == parent_name.lower() or n.name == cand:
                            matched_nodes.append(n)

            # 2. Search in AST parser if not in graph
            ast_matches = []
            if not matched_nodes:
                ast_matches = self._find_in_ast(parent_name=parent_name, symbol_name=member_name)

            # Evaluate matches
            if len(matched_nodes) == 1:
                node = matched_nodes[0]
                p_cls = node.metadata.get("parent_class")
                sym = f"{p_cls}.{node.name}" if p_cls else node.name
                lines = f"{node.start_line}-{node.end_line}" if (node.start_line and node.end_line) else (str(node.start_line) if node.start_line else None)
                f_path = str(node.file_path).replace("\\", "/")
                return ResolvedTarget(
                    target=sym,
                    target_symbol=sym,
                    target_file=f_path,
                    target_lines=lines,
                    resolution_method="exact_qualified",
                    confidence=1.0,
                    raw_query=request,
                )
            elif len(matched_nodes) > 1:
                # Ambiguous across multiple nodes
                files = list({str(n.file_path).replace("\\", "/") for n in matched_nodes})
                cand_dicts = [
                    {"symbol": n.name, "file": str(n.file_path).replace("\\", "/"), "lines": f"{n.start_line}-{n.end_line}"}
                    for n in matched_nodes
                ]
                return ResolvedTarget(
                    target=cand,
                    target_symbol=cand,
                    target_file="",
                    target_lines=None,
                    resolution_method="ambiguous",
                    confidence=0.0,
                    is_ambiguous=True,
                    ambiguity_candidates=cand_dicts,
                    unverified=[f"Qualified symbol '{cand}' matches {len(matched_nodes)} entities across files: {files}"],
                    raw_query=request,
                )

            if len(ast_matches) == 1:
                m = ast_matches[0]
                p_cls = m.get("parent_symbol")
                sym = f"{p_cls}.{m['symbol_name']}" if p_cls else m["symbol_name"]
                lines = f"{m.get('start_line', 1)}-{m.get('end_line', 1)}"
                f_path = str(m.get("file_path", "")).replace("\\", "/")
                return ResolvedTarget(
                    target=sym,
                    target_symbol=sym,
                    target_file=f_path,
                    target_lines=lines,
                    resolution_method="exact_qualified",
                    confidence=1.0,
                    raw_query=request,
                )
            elif len(ast_matches) > 1:
                files = list({str(m.get("file_path", "")).replace("\\", "/") for m in ast_matches})
                return ResolvedTarget(
                    target=cand,
                    target_symbol=cand,
                    target_file="",
                    target_lines=None,
                    resolution_method="ambiguous",
                    confidence=0.0,
                    is_ambiguous=True,
                    ambiguity_candidates=ast_matches,
                    unverified=[f"Qualified symbol '{cand}' matches {len(ast_matches)} AST entities across files: {files}"],
                    raw_query=request,
                )

            # If user explicitly specified a qualified symbol that doesn't exist in graph/AST,
            # we respect the exact qualified symbol intention without falling through to semantic search!
            return ResolvedTarget(
                target=cand,
                target_symbol=cand,
                target_file="",
                target_lines=None,
                resolution_method="exact_qualified",
                confidence=0.5,
                unverified=[f"Qualified symbol '{cand}' was explicitly requested but could not be located in codebase."],
                raw_query=request,
            )

        return None

    # ==========================================================================
    # Priority 2: Exact Symbol + File / Class Context
    # ==========================================================================

    def _resolve_symbol_with_context(
        self,
        request: str,
        intent_target: Optional[str],
        graph: Optional[GraphStore],
    ) -> Optional[ResolvedTarget]:
        """Resolves symbols accompanied by file or class context (e.g. app/graph/builder.py:build)."""
        # Look for .py file reference
        file_match = re.search(r"([a-zA-Z0-9_/\\.]+\.py)(?:::|:)?([a-zA-Z0-9_.]*)", request)
        if not file_match:
            return None

        file_candidate = file_match.group(1).replace("\\", "/")
        sym_candidate = file_match.group(2).strip() if file_match.group(2) else ""

        if not sym_candidate and intent_target:
            cleaned_intent = _clean_token(intent_target)
            if not cleaned_intent.endswith(".py") and cleaned_intent:
                sym_candidate = cleaned_intent

        norm_fc = file_candidate.lower()

        # Find matching file in project
        matched_file = None
        for py_path in self.project_root.rglob("*.py"):
            parts = [p.lower() for p in py_path.parts]
            if any(p.startswith(".") or p in ("venv", "node_modules", "__pycache__") for p in parts):
                continue
            rel_p = str(py_path.relative_to(self.project_root)).replace("\\", "/")
            if rel_p.lower() == norm_fc or rel_p.lower().endswith(norm_fc):
                matched_file = rel_p
                break

        if not matched_file:
            matched_file = file_candidate

        # 1. Search graph for symbol in this file
        if graph:
            file_nodes = [
                n for n in graph.get_nodes()
                if n.file_path and (str(n.file_path).replace("\\", "/").lower() == norm_fc or str(n.file_path).replace("\\", "/").lower().endswith(norm_fc))
            ]
            if sym_candidate:
                sym_lower = sym_candidate.lower()
                matching_sym_nodes = [
                    n for n in file_nodes
                    if n.name.lower() == sym_lower or (n.metadata.get("parent_class") and f"{n.metadata['parent_class']}.{n.name}".lower() == sym_lower)
                ]
                if len(matching_sym_nodes) == 1:
                    node = matching_sym_nodes[0]
                    p_cls = node.metadata.get("parent_class")
                    sym = f"{p_cls}.{node.name}" if p_cls else node.name
                    lines = f"{node.start_line}-{node.end_line}" if (node.start_line and node.end_line) else (str(node.start_line) if node.start_line else None)
                    return ResolvedTarget(
                        target=sym,
                        target_symbol=sym,
                        target_file=str(node.file_path).replace("\\", "/"),
                        target_lines=lines,
                        resolution_method="symbol_with_context",
                        confidence=0.95,
                        raw_query=request,
                    )
            elif file_nodes:
                # File only
                first = file_nodes[0]
                p_cls = first.metadata.get("parent_class")
                sym = f"{p_cls}.{first.name}" if p_cls else first.name
                return ResolvedTarget(
                    target=file_candidate,
                    target_symbol=sym,
                    target_file=str(first.file_path).replace("\\", "/"),
                    target_lines="1",
                    resolution_method="symbol_with_context",
                    confidence=0.95,
                    raw_query=request,
                )

        # 2. Search AST in file
        target_file_path = self.project_root / matched_file
        if target_file_path.exists() and target_file_path.is_file():
            parser = PythonParser()
            file_info = parser.parse_file(str(target_file_path))
            if sym_candidate:
                sym_lower = sym_candidate.lower()
                for m in file_info.get("methods", []):
                    p_cls = m.get("parent_class")
                    if m.get("name", "").lower() == sym_lower or (p_cls and f"{p_cls}.{m['name']}".lower() == sym_lower):
                        sym_name = f"{p_cls}.{m['name']}" if p_cls else m["name"]
                        return ResolvedTarget(
                            target=sym_name,
                            target_symbol=sym_name,
                            target_file=matched_file,
                            target_lines=f"{m.get('start_line', 1)}-{m.get('end_line', 1)}",
                            resolution_method="symbol_with_context",
                            confidence=0.95,
                            raw_query=request,
                        )
                for fn in file_info.get("functions", []):
                    if fn.get("name", "").lower() == sym_lower:
                        return ResolvedTarget(
                            target=fn["name"],
                            target_symbol=fn["name"],
                            target_file=matched_file,
                            target_lines=f"{fn.get('start_line', 1)}-{fn.get('end_line', 1)}",
                            resolution_method="symbol_with_context",
                            confidence=0.95,
                            raw_query=request,
                        )
                for cls in file_info.get("classes", []):
                    if cls.get("name", "").lower() == sym_lower:
                        return ResolvedTarget(
                            target=cls["name"],
                            target_symbol=cls["name"],
                            target_file=matched_file,
                            target_lines=f"{cls.get('start_line', 1)}-{cls.get('end_line', 1)}",
                            resolution_method="symbol_with_context",
                            confidence=0.95,
                            raw_query=request,
                        )

            return ResolvedTarget(
                target=matched_file,
                target_symbol=Path(matched_file).stem,
                target_file=matched_file,
                target_lines="1",
                resolution_method="symbol_with_context",
                confidence=0.95,
                raw_query=request,
            )

        return None

    # ==========================================================================
    # Priority 3: Exact Unqualified Symbol
    # ==========================================================================

    def _resolve_exact_unqualified(
        self,
        request: str,
        intent_target: Optional[str],
        graph: Optional[GraphStore],
    ) -> Optional[ResolvedTarget]:
        """Resolves exact unqualified symbol names, flagging ambiguity if multiple exist."""
        candidate = None
        if intent_target and "." not in intent_target:
            cand_clean = _clean_token(intent_target)
            if cand_clean and not cand_clean.endswith(".py") and " " not in cand_clean:
                candidate = cand_clean

        if not candidate:
            token = _clean_token(request)
            if token and " " not in token and not token.endswith(".py"):
                candidate = token

        if not candidate:
            # Check for backticked single identifier
            bt_matches = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", request)
            if bt_matches:
                candidate = bt_matches[0]

        if not candidate or len(candidate) < 2:
            return None

        # Ignore common natural language stop words
        stop_words = {
            "the", "a", "an", "for", "in", "to", "of", "and", "or", "fix",
            "modify", "change", "update", "refactor", "improve", "test",
            "plan", "bug", "issue", "patch", "code", "file", "all", "what",
            "why", "who", "when", "where", "how", "this", "that", "it",
        }
        if candidate.lower() in stop_words:
            return None

        cand_lower = candidate.lower()

        # 1. Search in GraphStore
        matched_nodes = []
        if graph:
            nodes = graph.find_nodes_by_name(candidate)
            if not nodes:
                nodes = [
                    n for n in graph.get_nodes()
                    if n.node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS)
                    and n.name.lower() == cand_lower
                ]
            matched_nodes = nodes

        # 2. Search in AST parser
        ast_matches = []
        if not matched_nodes:
            ast_matches = self._find_in_ast(parent_name=None, symbol_name=candidate)

        # Disambiguate / Evaluate
        if len(matched_nodes) == 1:
            node = matched_nodes[0]
            p_cls = node.metadata.get("parent_class")
            sym = f"{p_cls}.{node.name}" if p_cls else node.name
            lines = f"{node.start_line}-{node.end_line}" if (node.start_line and node.end_line) else (str(node.start_line) if node.start_line else None)
            return ResolvedTarget(
                target=sym,
                target_symbol=sym,
                target_file=str(node.file_path).replace("\\", "/"),
                target_lines=lines,
                resolution_method="exact_unqualified",
                confidence=0.90,
                raw_query=request,
            )
        elif len(matched_nodes) > 1:
            # Check if all matches are in the exact same file
            files = list({str(n.file_path).replace("\\", "/") for n in matched_nodes})
            cand_dicts = [
                {
                    "symbol": f"{n.metadata.get('parent_class')}.{n.name}" if n.metadata.get("parent_class") else n.name,
                    "file": str(n.file_path).replace("\\", "/"),
                    "lines": f"{n.start_line}-{n.end_line}",
                }
                for n in matched_nodes
            ]
            return ResolvedTarget(
                target=candidate,
                target_symbol=candidate,
                target_file="",
                target_lines=None,
                resolution_method="ambiguous",
                confidence=0.0,
                is_ambiguous=True,
                ambiguity_candidates=cand_dicts,
                unverified=[f"Unqualified symbol '{candidate}' is ambiguous and matches {len(matched_nodes)} definitions across {len(files)} files: {files}"],
                raw_query=request,
            )

        if len(ast_matches) == 1:
            m = ast_matches[0]
            p_cls = m.get("parent_symbol")
            sym = f"{p_cls}.{m['symbol_name']}" if p_cls else m["symbol_name"]
            lines = f"{m.get('start_line', 1)}-{m.get('end_line', 1)}"
            f_path = str(m.get("file_path", "")).replace("\\", "/")
            return ResolvedTarget(
                target=sym,
                target_symbol=sym,
                target_file=f_path,
                target_lines=lines,
                resolution_method="exact_unqualified",
                confidence=0.90,
                raw_query=request,
            )
        elif len(ast_matches) > 1:
            files = list({str(m.get("file_path", "")).replace("\\", "/") for m in ast_matches})
            return ResolvedTarget(
                target=candidate,
                target_symbol=candidate,
                target_file="",
                target_lines=None,
                resolution_method="ambiguous",
                confidence=0.0,
                is_ambiguous=True,
                ambiguity_candidates=ast_matches,
                unverified=[f"Unqualified symbol '{candidate}' is ambiguous and matches {len(ast_matches)} definitions across {len(files)} files: {files}"],
                raw_query=request,
            )

        # If candidate was an explicit single identifier (e.g. invented_module_name),
        # but not found in graph or AST, return an unverified result rather than
        # letting semantic search hallucinate a match.
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", candidate):
            return ResolvedTarget(
                target=candidate,
                target_symbol=candidate,
                target_file="",
                target_lines=None,
                resolution_method="exact_unqualified",
                confidence=0.0,
                is_ambiguous=False,
                unverified=["Target symbol or file could not be verified in the codebase"],
                raw_query=request,
            )

        return None

    # ==========================================================================
    # Priority 4: Semantic Search
    # ==========================================================================

    def _resolve_semantic_search(
        self,
        request: str,
        intent_target: Optional[str],
        graph: Optional[GraphStore],
    ) -> Optional[ResolvedTarget]:
        """Resolves natural language queries using semantic search."""
        search_query = intent_target if (intent_target and len(intent_target.split()) > 1) else request
        try:
            from app.search.hybrid_search import HybridCodeSearchEngine
            engine = HybridCodeSearchEngine(project_root=self.project_root, graph=graph)
            res = engine.search(query=search_query, top_k=3)
            if res and res.results:
                first = res.results[0]
                if first.score >= 0.60:
                    lines = f"{first.start_line}-{first.end_line}"
                    f_path = str(first.file).replace("\\", "/")
                    return ResolvedTarget(
                        target=first.symbol,
                        target_symbol=first.symbol,
                        target_file=f_path,
                        target_lines=lines,
                        resolution_method="semantic_search",
                        confidence=round(first.score, 4),
                        raw_query=request,
                    )
        except Exception:
            pass

        return None

    # ==========================================================================
    # Helper AST Lookup
    # ==========================================================================

    def _find_in_ast(
        self,
        parent_name: Optional[str],
        symbol_name: str,
    ) -> List[Dict[str, Any]]:
        """Scans Python files in project_root for matching AST symbols."""
        results: List[Dict[str, Any]] = []
        p_lower = parent_name.lower() if parent_name else None
        s_lower = symbol_name.lower()

        parser = PythonParser()
        for py_path in self.project_root.rglob("*.py"):
            parts = [p.lower() for p in py_path.parts]
            if any(p.startswith(".") or p in ("venv", "node_modules", "__pycache__") for p in parts):
                continue

            try:
                rel_p = str(py_path.relative_to(self.project_root)).replace("\\", "/")
                file_info = parser.parse_file(str(py_path))
                if "error" in file_info:
                    continue

                if p_lower:
                    # Looking for method in class
                    for m in file_info.get("methods", []):
                        m_cls = (m.get("parent_class") or "").lower()
                        m_name = m.get("name", "").lower()
                        if m_cls == p_lower and m_name == s_lower:
                            results.append({
                                "symbol_name": m.get("name"),
                                "parent_symbol": m.get("parent_class"),
                                "file_path": rel_p,
                                "start_line": m.get("start_line", 1),
                                "end_line": m.get("end_line", 1),
                            })
                    # Looking for class if symbol_name is class
                    for cls in file_info.get("classes", []):
                        if cls.get("name", "").lower() == f"{p_lower}.{s_lower}":
                            results.append({
                                "symbol_name": cls.get("name"),
                                "parent_symbol": None,
                                "file_path": rel_p,
                                "start_line": cls.get("start_line", 1),
                                "end_line": cls.get("end_line", 1),
                            })
                else:
                    # Looking for function, class, or method matching symbol_name
                    for fn in file_info.get("functions", []):
                        if fn.get("name", "").lower() == s_lower:
                            results.append({
                                "symbol_name": fn.get("name"),
                                "parent_symbol": None,
                                "file_path": rel_p,
                                "start_line": fn.get("start_line", 1),
                                "end_line": fn.get("end_line", 1),
                            })
                    for cls in file_info.get("classes", []):
                        if cls.get("name", "").lower() == s_lower:
                            results.append({
                                "symbol_name": cls.get("name"),
                                "parent_symbol": None,
                                "file_path": rel_p,
                                "start_line": cls.get("start_line", 1),
                                "end_line": cls.get("end_line", 1),
                            })
                    for m in file_info.get("methods", []):
                        if m.get("name", "").lower() == s_lower:
                            results.append({
                                "symbol_name": m.get("name"),
                                "parent_symbol": m.get("parent_class"),
                                "file_path": rel_p,
                                "start_line": m.get("start_line", 1),
                                "end_line": m.get("end_line", 1),
                            })
            except Exception:
                continue

        return results
