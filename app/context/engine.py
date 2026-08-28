"""
DevPilot Repository Intelligence & Context Engine.

Aggregates symbol definitions, bounded source code snippets, dependency graph relationships,
related test coverage discovery, and Git change history into a unified repository context.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.agent.intent import classify_question_intent
from app.agent.tools import resolve_safe_path
from app.context.models import (
    GitChangeContext,
    RelatedTest,
    RepositoryContext,
    SourceSnippet,
    SymbolContext,
)
from app.graph.models import NodeType
from app.graph.queries import (
    get_callees,
    get_callers,
    get_dependencies,
    get_dependents,
    get_impact,
)
from app.graph.store import GraphStore
from app.parser.python_parser import PythonParser


class ContextEngine:
    """
    Core repository context aggregation engine.
    Collects targeted symbol definitions, source snippets, dependency graph intelligence,
    test coverage discovery, and Git history without full-repository dumping.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        graph: Optional[GraphStore] = None,
        max_snippet_lines: int = 50,
        max_items_per_category: int = 5,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self._graph = graph
        self.max_snippet_lines = max_snippet_lines
        self.max_items_per_category = max_items_per_category
        self._parser = PythonParser()

    def _get_active_graph(self) -> Optional[GraphStore]:
        """Resolves or lazily constructs the codebase dependency graph."""
        if self._graph is not None:
            return self._graph

        from app.graph.builder import GraphBuilder
        default_graph_path = self.project_root / "data" / "graph.json"
        if default_graph_path.is_file():
            try:
                self._graph = GraphStore.load(default_graph_path)
                return self._graph
            except Exception:
                pass

        try:
            self._graph = GraphBuilder().build(self.project_root)
            return self._graph
        except Exception:
            return None

    def _extract_target_symbol_and_file(
        self,
        question: str,
        explicit_symbol: Optional[str] = None,
        explicit_file: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extracts candidate target symbol and target file from question or explicit args."""
        if explicit_symbol and explicit_symbol.strip():
            return explicit_symbol.strip(), explicit_file.strip() if explicit_file else None

        if explicit_file and explicit_file.strip():
            return None, explicit_file.strip()

        classification = classify_question_intent(question)
        target_sym = classification.target_symbol
        target_file = classification.target_file

        if not target_sym:
            # Fallback regex for dotted identifiers or CamelCase names
            patterns = [
                r"\b([A-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\b",  # e.g. GraphBuilder.build
                r"\b([A-Z][a-zA-Z0-9_]{2,})\b",                             # e.g. GraphBuilder
                r"\b([a-z_][a-z0-9_]{2,}\.[a-z_][a-z0-9_]*)\b",            # e.g. builder.build
            ]
            for p in patterns:
                m = re.search(p, question)
                if m:
                    candidate = m.group(1)
                    if candidate.lower() not in ("what", "which", "where", "explain", "python", "devpilot"):
                        target_sym = candidate
                        break

        if not target_file:
            file_match = re.search(r"[\w/\\]+\.py\b", question)
            if file_match:
                target_file = file_match.group(0)

        return target_sym, target_file

    def _collect_symbols_and_snippets(
        self,
        target_symbol: Optional[str],
        target_file: Optional[str],
    ) -> Tuple[List[SymbolContext], List[SourceSnippet], Optional[str]]:
        """Locates symbol definitions and extracts bounded source snippets."""
        symbols: List[SymbolContext] = []
        snippets: List[SourceSnippet] = []
        resolved_canonical_file: Optional[str] = target_file

        if not target_symbol and not target_file:
            return symbols, snippets, resolved_canonical_file

        graph = self._get_active_graph()
        leaf_name = target_symbol.split(".")[-1].lower() if target_symbol else ""

        # 1. Search graph nodes
        if graph and target_symbol:
            nodes = graph.find_nodes_by_name(leaf_name)
            if not nodes and "." in target_symbol:
                nodes = graph.find_nodes_by_name(target_symbol.lower())

            for node in nodes[:self.max_items_per_category]:
                if node.node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                    parent_cls = node.metadata.get("parent_class")
                    code_snippet = ""
                    if node.file_path and node.start_line:
                        code_snippet = self._read_source_slice(node.file_path, node.start_line, node.end_line or node.start_line + 30)
                        if not resolved_canonical_file:
                            resolved_canonical_file = node.file_path

                    sym_ctx = SymbolContext(
                        name=node.name,
                        file_path=node.file_path,
                        symbol_type=node.node_type.value.lower(),
                        parent_symbol=parent_cls,
                        start_line=node.start_line,
                        end_line=node.end_line,
                        code=code_snippet,
                    )
                    symbols.append(sym_ctx)

                    if code_snippet:
                        snippets.append(SourceSnippet(
                            file_path=node.file_path,
                            start_line=node.start_line or 1,
                            end_line=node.end_line or (node.start_line or 1) + 20,
                            code=code_snippet,
                            symbol_name=node.name,
                        ))

        # 2. If not found in graph, search via AST parsing across python files
        if not symbols and target_symbol and self.project_root.exists():
            py_files = list(self.project_root.rglob("*.py"))
            for pf in py_files:
                if len(symbols) >= self.max_items_per_category:
                    break
                rel_p = pf.relative_to(self.project_root).as_posix()
                if rel_p.startswith((".venv", "venv", ".git", "build", "dist")):
                    continue
                try:
                    parsed = self._parser.parse_file(str(pf))
                    # Classes
                    for cls in parsed.get("classes", []):
                        if cls["name"].lower() == leaf_name or (target_symbol and cls["name"].lower() in target_symbol.lower()):
                            s_line = cls.get("line_number", 1)
                            code_snip = self._read_source_slice(rel_p, s_line, s_line + self.max_snippet_lines)
                            symbols.append(SymbolContext(
                                name=cls["name"],
                                file_path=rel_p,
                                symbol_type="class",
                                start_line=s_line,
                                code=code_snip,
                            ))
                            if not resolved_canonical_file:
                                resolved_canonical_file = rel_p
                    # Functions & Methods
                    all_funcs = parsed.get("functions", []) + parsed.get("methods", [])
                    for fn in all_funcs:
                        if fn["name"].lower() == leaf_name:
                            s_line = fn.get("line_number", 1)
                            code_snip = self._read_source_slice(rel_p, s_line, s_line + self.max_snippet_lines)
                            symbols.append(SymbolContext(
                                name=fn["name"],
                                file_path=rel_p,
                                symbol_type="method" if "class_name" in fn else "function",
                                parent_symbol=fn.get("class_name"),
                                start_line=s_line,
                                code=code_snip,
                            ))
                            if not resolved_canonical_file:
                                resolved_canonical_file = rel_p
                except Exception:
                    continue

        # 3. Target file fallback snippet
        if not snippets and resolved_canonical_file:
            file_snip = self._read_source_slice(resolved_canonical_file, 1, self.max_snippet_lines)
            if file_snip:
                snippets.append(SourceSnippet(
                    file_path=resolved_canonical_file,
                    start_line=1,
                    end_line=self.max_snippet_lines,
                    code=file_snip,
                ))

        return symbols, snippets, resolved_canonical_file

    def _read_source_slice(self, rel_path: str, start_line: int, end_line: int) -> str:
        """Reads a bounded slice of source code safely."""
        try:
            target = resolve_safe_path(rel_path, project_root=self.project_root)
            if not target.is_file():
                return ""
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            s_idx = max(0, start_line - 1)
            e_idx = min(len(lines), end_line, s_idx + self.max_snippet_lines)
            return "\n".join(lines[s_idx:e_idx])
        except Exception:
            return ""

    def _collect_graph_relationships(
        self,
        target_symbol: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]], List[str]]:
        """Queries graph callers, callees, dependencies, dependents, and impact."""
        callers: List[Dict[str, Any]] = []
        callees: List[Dict[str, Any]] = []
        dependencies: List[Dict[str, Any]] = []
        dependents: List[Dict[str, Any]] = []
        impact_data: Optional[Dict[str, Any]] = None
        impacted_files: List[str] = []

        if not target_symbol:
            return callers, callees, dependencies, dependents, impact_data, impacted_files

        graph = self._get_active_graph()
        if not graph:
            return callers, callees, dependencies, dependents, impact_data, impacted_files

        try:
            callers = get_callers(graph, symbol=target_symbol)[:self.max_items_per_category]
        except Exception:
            pass

        try:
            callees = get_callees(graph, symbol=target_symbol)[:self.max_items_per_category]
        except Exception:
            pass

        try:
            dep_res = get_dependencies(graph, symbol=target_symbol, depth=2)
            dependencies = dep_res.get("dependencies", [])[:self.max_items_per_category]
        except Exception:
            pass

        try:
            dep_res = get_dependents(graph, symbol=target_symbol, depth=2)
            dependents = dep_res.get("dependents", [])[:self.max_items_per_category]
        except Exception:
            pass

        try:
            impact_data = get_impact(graph, symbol=target_symbol, depth=2)
            impacted_files = impact_data.get("impacted_files", [])[:self.max_items_per_category]
        except Exception:
            pass

        return callers, callees, dependencies, dependents, impact_data, impacted_files

    def _discover_related_tests(
        self,
        target_symbol: Optional[str],
        target_file: Optional[str],
    ) -> List[RelatedTest]:
        """Discovers test files and test functions covering the target symbol or file."""
        related_tests: List[RelatedTest] = []
        if not self.project_root.exists():
            return related_tests

        tests_dir = self.project_root / "tests"
        if not tests_dir.is_dir():
            return related_tests

        # Normalize search keys
        symbol_tokens = [t.lower() for t in (target_symbol or "").replace(".", " ").replace("_", " ").split() if len(t) > 2]
        file_stem = Path(target_file).stem.lower().replace("test_", "") if target_file else ""

        test_files = list(tests_dir.glob("test_*.py")) + list(tests_dir.glob("*_test.py"))
        seen_tests: Set[Tuple[str, Optional[str]]] = set()

        for tf in test_files:
            rel_test_path = tf.relative_to(self.project_root).as_posix()
            stem = tf.stem.lower()

            # 1. Check filename relevance
            is_file_match = bool(file_stem and file_stem in stem)
            is_symbol_match = any(token in stem for token in symbol_tokens) if symbol_tokens else False

            if is_file_match or is_symbol_match:
                reason = "test filename matches target module" if is_file_match else "test filename matches target symbol"
                key = (rel_test_path, None)
                if key not in seen_tests:
                    seen_tests.add(key)
                    related_tests.append(RelatedTest(
                        test_file=rel_test_path,
                        reason=reason,
                    ))

            # 2. Inspect test functions via AST
            try:
                parsed = self._parser.parse_file(str(tf))
                for fn in parsed.get("functions", []):
                    fn_name = fn["name"].lower()
                    if fn_name.startswith("test_"):
                        fn_matches = any(tok in fn_name for tok in symbol_tokens) if symbol_tokens else False
                        if fn_matches or (file_stem and file_stem in fn_name):
                            key = (rel_test_path, fn["name"])
                            if key not in seen_tests:
                                seen_tests.add(key)
                                related_tests.append(RelatedTest(
                                    test_file=rel_test_path,
                                    test_function=fn["name"],
                                    line_number=fn.get("line_number"),
                                    reason=f"test function covers '{target_symbol or file_stem}'",
                                ))
            except Exception:
                continue

            if len(related_tests) >= self.max_items_per_category * 2:
                break

        return related_tests[:self.max_items_per_category]

    def _collect_git_intelligence(
        self,
        target_file: Optional[str],
    ) -> Tuple[List[GitChangeContext], List[GitChangeContext]]:
        """Safely retrieves file history and recent repository commits using app.git."""
        git_history: List[GitChangeContext] = []
        recent_changes: List[GitChangeContext] = []

        from app.git.history import get_file_history, get_recent_commits
        from app.git.repository import NotAGitRepositoryError, get_repository, is_git_repository

        if not is_git_repository(self.project_root):
            return git_history, recent_changes

        try:
            repo = get_repository(self.project_root)
        except NotAGitRepositoryError:
            return git_history, recent_changes

        # 1. Target file history
        if target_file:
            try:
                commits = get_file_history(repo=repo, file_path=target_file, limit=self.max_items_per_category)
                for c in commits:
                    git_history.append(GitChangeContext(
                        commit_hash=c.commit_hash,
                        short_hash=c.short_hash,
                        author=c.author_name,
                        date=c.date,
                        message=c.message,
                        files_changed=c.files_changed,
                    ))
            except Exception:
                pass

        # 2. General recent repository changes
        try:
            recent = get_recent_commits(repo=repo, limit=self.max_items_per_category)
            for c in recent:
                recent_changes.append(GitChangeContext(
                    commit_hash=c.commit_hash,
                    short_hash=c.short_hash,
                    author=c.author_name,
                    date=c.date,
                    message=c.message,
                    files_changed=c.files_changed,
                ))
        except Exception:
            pass

        return git_history, recent_changes

    def build_context(
        self,
        question: str,
        symbol: Optional[str] = None,
        file_path: Optional[str] = None,
        project_dir: Optional[Union[str, Path]] = None,
        include_git: bool = True,
        include_graph: bool = True,
        include_tests: bool = True,
    ) -> RepositoryContext:
        """
        Builds a structured RepositoryContext combining symbols, sources,
        graph relationships, related tests, and Git history.
        """
        q = (question or "").strip()
        if not q and not symbol and not file_path:
            raise ValueError("Question, symbol, or file_path must be provided.")

        if project_dir:
            self.project_root = Path(project_dir).resolve()

        if not self.project_root.exists():
            raise ValueError(f"Project directory does not exist: '{self.project_root}'")

        # Step 1: Identify target symbol and target file
        target_sym, target_f = self._extract_target_symbol_and_file(
            question=q,
            explicit_symbol=symbol,
            explicit_file=file_path,
        )

        # Step 2: Retrieve symbol definitions and source snippets
        symbols, snippets, resolved_file = self._collect_symbols_and_snippets(
            target_symbol=target_sym,
            target_file=target_f,
        )

        # Step 3: Query graph relationships
        callers, callees, deps, dependents, impact, impacted_files = [], [], [], [], None, []
        if include_graph:
            callers, callees, deps, dependents, impact, impacted_files = self._collect_graph_relationships(
                target_symbol=target_sym,
            )

        # Step 4: Discover related tests
        related_tests: List[RelatedTest] = []
        if include_tests:
            related_tests = self._discover_related_tests(
                target_symbol=target_sym,
                target_file=resolved_file or target_f,
            )

        # Step 5: Collect Git change history
        git_history: List[GitChangeContext] = []
        recent_changes: List[GitChangeContext] = []
        if include_git:
            git_history, recent_changes = self._collect_git_intelligence(
                target_file=resolved_file or target_f,
            )

        # Step 6: Summary statistics
        summary = {
            "target_symbol": target_sym,
            "target_file": resolved_file or target_f,
            "symbols_found": len(symbols),
            "snippets_retrieved": len(snippets),
            "callers_count": len(callers),
            "callees_count": len(callees),
            "dependencies_count": len(deps),
            "dependents_count": len(dependents),
            "impacted_files_count": len(impacted_files),
            "related_tests_count": len(related_tests),
            "git_commits_count": len(git_history) if git_history else len(recent_changes),
        }

        return RepositoryContext(
            question=q,
            target_symbol=target_sym,
            target_file=resolved_file or target_f,
            symbols=symbols,
            source_snippets=snippets,
            callers=callers,
            callees=callees,
            dependencies=deps,
            dependents=dependents,
            impact=impact,
            impacted_files=impacted_files,
            related_tests=related_tests,
            git_history=git_history,
            recent_changes=recent_changes,
            summary=summary,
        )
