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
    get_dependents,
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


def test_get_dependents():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _setup_test_project(root)

        graph = GraphBuilder().build(root)

        # Dependents of verify_pw (who calls it upstream): authenticate, login_handler
        deps = get_dependents(graph, "verify_pw", depth=2)
        assert deps["total_dependents"] >= 1
        dep_names = [d["name"] for d in deps["dependents"]]
        assert "authenticate" in dep_names


def test_cycle_handling():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "cyclic.py").write_text("""
def func_a():
    return func_b()

def func_b():
    return func_a()
""", encoding="utf-8")

        graph = GraphBuilder().build(root)
        # Should not hang in infinite loop on cycles
        dep = get_dependencies(graph, "func_a", depth=5)
        assert dep["total_dependencies"] == 2
        names = [d["name"] for d in dep["dependencies"]]
        assert "func_b" in names
        assert "func_a" in names


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


def test_ambiguous_symbols_handling():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "mod1.py").write_text("def common_name(): pass\n", encoding="utf-8")
        (root / "mod2.py").write_text("def common_name(): pass\n", encoding="utf-8")

        graph = GraphBuilder().build(root)
        # If searching by ambiguous short name without specifying file, get_dependencies returns error note
        res = get_dependencies(graph, "common_name", depth=1)
        assert "error" in res or res["total_dependencies"] == 0


def test_get_impact_regression_graphbuilder_build():
    """Regression test: verifies get_impact resolves GraphBuilder.build, bare build, and qualified symbol."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "builder.py").write_text("""
class GraphBuilder:
    def build(self, path):
        return f"graph_{path}"

def helper():
    return GraphBuilder().build("root")
""", encoding="utf-8")
        (root / "caller_service.py").write_text("""
from builder import helper, GraphBuilder

def run_service():
    helper()
    return GraphBuilder().build("service")
""", encoding="utf-8")

        graph = GraphBuilder().build(root)

        # 1. By class.method name
        impact_cls = get_impact(graph, "GraphBuilder.build", depth=2)
        assert impact_cls["total_impacted"] >= 2
        direct_names = [c["name"] for c in impact_cls["direct_callers"]]
        assert "helper" in direct_names
        assert "run_service" in direct_names
        assert "builder.py" in impact_cls["impacted_files"]
        assert "caller_service.py" in impact_cls["impacted_files"]

        # 2. By file::class.method qualified format
        impact_qual = get_impact(graph, "builder.py::GraphBuilder.build", depth=2)
        assert impact_qual["total_impacted"] >= 2
        direct_qual = [c["name"] for c in impact_qual["direct_callers"]]
        assert "helper" in direct_qual
        assert "run_service" in direct_qual

        # 3. By file:class.method format
        impact_colon = get_impact(graph, "builder.py:GraphBuilder.build", depth=2)
        assert impact_colon["total_impacted"] >= 2

        # 4. By callers
        callers = get_callers(graph, "builder.py::GraphBuilder.build")
        caller_names = [c["name"] for c in callers]
        assert "helper" in caller_names
        assert "run_service" in caller_names


def test_get_impact_on_project_graph():
    """Verifies get_impact on actual project GraphBuilder.build."""
    project_root = Path(__file__).resolve().parent.parent
    graph = GraphBuilder().build(project_root)

    impact = get_impact(graph, "app/graph/builder.py::GraphBuilder.build", depth=2)
    assert impact["total_impacted"] > 0
    direct_names = [c["name"] for c in impact["direct_callers"]]
    assert "_resolve_graph" in direct_names
    assert "_load_or_build_graph" in direct_names
    assert "run_graph_build" in direct_names
    assert "app/agent/tools.py" in impact["impacted_files"]
    assert "app/main.py" in impact["impacted_files"]


def test_graphbuilder_build_dependencies_accuracy():
    """
    Regression test verifying dependencies of GraphBuilder.build:
    - ProjectScanner.scan in app/scanner/scanner.py
    - No false ToolRegistry.get
    - No standard-library method false positives
    - Exact call-site line numbers
    """
    project_root = Path(__file__).resolve().parent.parent
    graph = GraphBuilder().build(project_root)

    deps = get_dependencies(graph, "GraphBuilder.build", depth=1)
    dep_items = deps["dependencies"]
    dep_names = {d["name"] for d in dep_items}
    dep_files = {d["file_path"] for d in dep_items}
    dep_ids = {d["id"] for d in dep_items}

    # 1. Verify ProjectScanner.scan is from app/scanner/scanner.py
    assert "scan" in dep_names
    scan_dep = next(d for d in dep_items if d["name"] == "scan")
    assert scan_dep["file_path"] == "app/scanner/scanner.py"
    assert scan_dep["call_line"] == 55
    assert scan_dep["node_type"] == "METHOD"

    # 2. Verify ASTExtractor.extract_file
    assert "extract_file" in dep_names
    extract_dep = next(d for d in dep_items if d["name"] == "extract_file")
    assert extract_dep["file_path"] == "app/graph/extractor.py"
    assert extract_dep["call_line"] == 68

    # 3. Verify GraphStore constructor
    assert "GraphStore" in dep_names
    store_cls_dep = next(d for d in dep_items if d["name"] == "GraphStore" and d["node_type"] == "CLASS")
    assert store_cls_dep["file_path"] == "app/graph/store.py"
    assert store_cls_dep["call_line"] == 46

    # 4. Verify no false ToolRegistry.get dependency
    assert not any("ToolRegistry" in d_id or "tool_registry.py" in d_file for d_id, d_file in zip(dep_ids, dep_files))

    # 5. Verify all call lines are valid positive integers
    for d in dep_items:
        assert isinstance(d["call_line"], int) and d["call_line"] > 0


