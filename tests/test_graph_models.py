"""
Tests for DevPilot Graph Models.
"""

from app.graph.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    make_class_node_id,
    make_file_node_id,
    make_function_node_id,
    make_method_node_id,
    make_module_node_id,
    normalize_graph_path,
)


def test_deterministic_node_ids():
    assert make_file_node_id("backend\\auth.py") == "file:backend/auth.py"
    assert make_file_node_id("backend/auth.py") == "file:backend/auth.py"
    assert make_module_node_id("os") == "module:os"
    assert make_class_node_id("backend/auth.py", "AuthService") == "class:backend/auth.py:AuthService"
    assert make_function_node_id("backend/auth.py", "login_user") == "function:backend/auth.py:login_user"
    assert make_method_node_id("backend/auth.py", "AuthService", "verify") == "method:backend/auth.py:AuthService.verify"


def test_graph_node_serialization():
    node = GraphNode(
        id="function:auth.py:login",
        node_type=NodeType.FUNCTION,
        name="login",
        file_path="auth.py",
        start_line=10,
        end_line=20,
        parent_id="file:auth.py",
        metadata={"async": True},
    )

    d = node.to_dict()
    assert d["id"] == "function:auth.py:login"
    assert d["node_type"] == "FUNCTION"
    assert d["name"] == "login"
    assert d["metadata"]["async"] is True

    reconstructed = GraphNode.from_dict(d)
    assert reconstructed.id == node.id
    assert reconstructed.node_type == NodeType.FUNCTION
    assert reconstructed.start_line == 10
    assert reconstructed.end_line == 20
    assert reconstructed.metadata == {"async": True}


def test_graph_edge_serialization():
    edge = GraphEdge(
        source_id="function:auth.py:login",
        target_id="function:auth.py:hash_password",
        edge_type=EdgeType.CALLS,
        file_path="auth.py",
        line_number=15,
        metadata={"call_type": "direct"},
    )

    d = edge.to_dict()
    assert d["source_id"] == "function:auth.py:login"
    assert d["target_id"] == "function:auth.py:hash_password"
    assert d["edge_type"] == "CALLS"
    assert d["line_number"] == 15

    reconstructed = GraphEdge.from_dict(d)
    assert reconstructed.source_id == edge.source_id
    assert reconstructed.target_id == edge.target_id
    assert reconstructed.edge_type == EdgeType.CALLS
    assert reconstructed.line_number == 15
