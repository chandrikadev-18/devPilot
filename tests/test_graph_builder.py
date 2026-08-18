"""
Tests for GraphBuilder and GraphStore.
"""

from pathlib import Path
import tempfile

from app.graph.builder import GraphBuilder
from app.graph.models import EdgeType, NodeType
from app.graph.store import GraphStore


def test_build_and_link_project_graph():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        utils_py = root / "utils.py"
        utils_py.write_text("""
def hash_string(val):
    return "hashed_" + str(val)
""", encoding="utf-8")

        auth_py = root / "auth.py"
        auth_py.write_text("""
from utils import hash_string

class AuthService:
    def verify_token(self, token):
        return True

    def login(self, username, password):
        h = hash_string(password)
        return self.verify_token(h)

def login_user(u, p):
    svc = AuthService()
    return svc.login(u, p)
""", encoding="utf-8")

        builder = GraphBuilder()
        graph = builder.build(root)

        # Check nodes
        nodes = graph.get_nodes()
        node_ids = {n.id for n in nodes}

        assert "file:utils.py" in node_ids
        assert "file:auth.py" in node_ids
        assert "function:utils.py:hash_string" in node_ids
        assert "class:auth.py:AuthService" in node_ids
        assert "method:auth.py:AuthService.login" in node_ids
        assert "method:auth.py:AuthService.verify_token" in node_ids
        assert "function:auth.py:login_user" in node_ids

        # Check structural edges
        contains_edges = graph.get_edges(EdgeType.CONTAINS)
        contains_tuples = {(e.source_id, e.target_id) for e in contains_edges}
        assert ("file:auth.py", "class:auth.py:AuthService") in contains_tuples
        assert ("class:auth.py:AuthService", "method:auth.py:AuthService.login") in contains_tuples

        # Check import edges
        import_edges = graph.get_edges(EdgeType.IMPORTS)
        import_tuples = {(e.source_id, e.target_id) for e in import_edges}
        assert ("file:auth.py", "file:utils.py") in import_tuples

        # Check resolved calls edges
        calls_edges = graph.get_edges(EdgeType.CALLS)
        calls_tuples = {(e.source_id, e.target_id) for e in calls_edges}

        # login calls verify_token (same class method)
        assert ("method:auth.py:AuthService.login", "method:auth.py:AuthService.verify_token") in calls_tuples

        # login calls hash_string (imported function)
        assert ("method:auth.py:AuthService.login", "function:utils.py:hash_string") in calls_tuples

        # Save and reload
        save_path = root / "graph.json"
        graph.save(save_path)
        assert save_path.is_file()

        loaded_graph = GraphStore.load(save_path)
        assert len(loaded_graph.get_nodes()) == len(nodes)
        assert len(loaded_graph.get_edges()) == len(graph.get_edges())
