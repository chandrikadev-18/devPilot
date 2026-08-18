"""
Tests for Graph Queries (callers, callees, dependencies, impact, file dependencies).
"""

from pathlib import Path
import tempfile

from app.graph.builder import GraphBuilder
from app.graph.queries import (
    get_callees,
    get_callers,
    get_dependencies,
    get_file_dependencies,
    get_impact,
)


def _setup_test_project(tmp_path: Path):
    (tmp_path / "crypto.py").write_text("""
def hash_val(x):
    return f"h_{x}"
""", encoding="utf-8")

    (tmp_path / "auth.py").write_text("""
from crypto import hash_val

def verify_pw(pw):
    return hash_val(pw) == "h_secret"

def authenticate(user, pw):
    return verify_pw(pw)
""", encoding="utf-8")

    (tmp_path / "api.py").write_text("""
from auth import authenticate

def login_handler(req):
    return authenticate(req.user, req.pw)

def api_entrypoint(req):
    return login_handler(req)
""", encoding="utf-8")


def test_get_callers_and_callees():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _setup_test_project(root)

        graph = GraphBuilder().build(root)

        # Callers of verify_pw
        callers = get_callers(graph, "verify_pw")
        caller_names = [c["name"] for c in callers]
        assert "authenticate" in caller_names

        # Callees of authenticate
        callees = get_callees(graph, "authenticate")
        callee_names = [c["name"] for c in callees]
        assert "verify_pw" in callee_names


def test_get_dependencies_with_depth():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _setup_test_project(root)

        graph = GraphBuilder().build(root)

        # Depth 1 from api_entrypoint -> login_handler
        dep1 = get_dependencies(graph, "api_entrypoint", depth=1)
        assert dep1["total_dependencies"] == 1
        assert dep1["dependencies"][0]["name"] == "login_handler"

        # Depth 3 from api_entrypoint -> login_handler -> authenticate -> verify_pw
        dep3 = get_dependencies(graph, "api_entrypoint", depth=3)
        dep_names = [d["name"] for d in dep3["dependencies"]]
        assert "login_handler" in dep_names
        assert "authenticate" in dep_names
        assert "verify_pw" in dep_names


def test_get_impact_analysis():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _setup_test_project(root)

        graph = GraphBuilder().build(root)

        # Impact of modifying hash_val:
        # Direct: verify_pw
        # Indirect: authenticate, login_handler
        impact = get_impact(graph, "hash_val", depth=3)
        direct = [c["name"] for c in impact["direct_callers"]]
        indirect = [c["name"] for c in impact["indirect_callers"]]

        assert "verify_pw" in direct
        assert "authenticate" in indirect or "login_handler" in indirect
        assert "auth.py" in impact["impacted_files"]


def test_get_file_dependencies():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _setup_test_project(root)

        graph = GraphBuilder().build(root)

        file_deps = get_file_dependencies(graph, "auth.py")
        assert "crypto.py" in file_deps["imports_files"]
        assert "api.py" in file_deps["imported_by"]
        symbol_names = [s["name"] for s in file_deps["defined_symbols"]]
        assert "verify_pw" in symbol_names
        assert "authenticate" in symbol_names
