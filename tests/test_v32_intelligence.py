"""
DevPilot v3.2 Advanced Code Intelligence Regression Suite.

Tests hybrid retrieval, stemming, token co-occurrence scoring, AST parsing,
dependency traversal, and explainable context construction on real repository artifacts.
"""

from pathlib import Path
import pytest

from app.graph.builder import GraphBuilder
from app.graph.queries import get_callers, get_callees, get_dependencies, get_impact
from app.search.hybrid_search import HybridCodeSearchEngine, _stem_token, _extract_query_keywords
from app.context.engine import ContextEngine


def test_stem_token_precision():
    assert _stem_token("scanning") == "scan"
    assert _stem_token("scanner") == "scan"
    assert _stem_token("building") == "build"
    assert _stem_token("builder") == "build"
    assert _stem_token("construction") == "construct"
    assert _stem_token("operations") == "operat"
    assert _stem_token("dependencies") == "dependenc"


def test_extract_query_keywords_filters_stopwords():
    tokens = _extract_query_keywords("Where is project scanning implemented?")
    assert "project" in tokens
    assert "scanning" in tokens
    assert "where" not in tokens
    assert "is" not in tokens


def test_hybrid_search_precision_on_sample_project(tmp_path):
    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        "class AuthService:\n"
        "    def hash_password(self, password):\n"
        "        return password + '_hash'\n"
        "    def verify_password(self, password, hashed):\n"
        "        return self.hash_password(password) == hashed\n",
        encoding="utf-8"
    )

    engine = HybridCodeSearchEngine(searcher=None, project_root=tmp_path)
    res = engine.search("Where is password hashing handled?", top_k=5)
    assert len(res.results) > 0
    top_syms = [r.symbol for r in res.results]
    assert any("hash_password" in s or "AuthService" in s for s in top_syms)


def test_graph_builder_and_dependency_traversal_on_mock(tmp_path):
    builder_py = tmp_path / "builder.py"
    builder_py.write_text(
        "class GraphBuilder:\n"
        "    def build(self):\n"
        "        return self._link_nodes()\n"
        "    def _link_nodes(self):\n"
        "        return []\n",
        encoding="utf-8"
    )

    store = GraphBuilder().build(tmp_path)
    nodes = store.get_nodes()
    assert len(nodes) >= 3

    callees = get_callees(store, "GraphBuilder.build")
    assert len(callees) == 1
    assert callees[0]["name"] == "_link_nodes"

    callers = get_callers(store, "GraphBuilder._link_nodes")
    assert len(callers) == 1
    assert callers[0]["name"] == "build"


def test_context_engine_aggregation(tmp_path):
    service_py = tmp_path / "scanner.py"
    service_py.write_text(
        "class ProjectScanner:\n"
        "    def scan(self, directory):\n"
        "        return {'files': 10}\n",
        encoding="utf-8"
    )

    engine = ContextEngine(project_root=tmp_path)
    ctx = engine.build_context("What does ProjectScanner.scan do?")
    assert ctx.target_symbol is not None
    assert "scan" in ctx.target_symbol.lower() or "projectscanner" in ctx.target_symbol.lower()
