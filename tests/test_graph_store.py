"""
Unit tests for GraphStore in-memory index, duplicate protection, and serialization.
"""

from pathlib import Path
import tempfile

from app.graph.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    make_class_node_id,
    make_file_node_id,
    make_function_node_id,
)
from app.graph.store import GraphStore


def test_store_duplicate_protection():
    store = GraphStore()

    n1 = GraphNode(
        id=make_file_node_id("app/main.py"),
        node_type=NodeType.FILE,
        name="main.py",
        file_path="app/main.py",
    )
    store.add_node(n1)
    store.add_node(n1)  # Duplicate node addition

    assert len(store.get_nodes()) == 1

    n2 = GraphNode(
        id=make_function_node_id("app/main.py", "run_scan"),
        node_type=NodeType.FUNCTION,
        name="run_scan",
        file_path="app/main.py",
    )
    store.add_node(n2)
    assert len(store.get_nodes()) == 2

    edge = GraphEdge(
        source_id=n1.id,
        target_id=n2.id,
        edge_type=EdgeType.DEFINES,
        file_path="app/main.py",
        line_number=50,
    )
    store.add_edge(edge)
    store.add_edge(edge)  # Duplicate edge addition

    assert len(store.get_edges()) == 1


def test_store_query_indexes():
    store = GraphStore()

    file_node = GraphNode(
        id=make_file_node_id("auth.py"),
        node_type=NodeType.FILE,
        name="auth.py",
        file_path="auth.py",
    )
    class_node = GraphNode(
        id=make_class_node_id("auth.py", "AuthService"),
        node_type=NodeType.CLASS,
        name="AuthService",
        file_path="auth.py",
        parent_id=file_node.id,
    )
    func_node = GraphNode(
        id=make_function_node_id("auth.py", "login"),
        node_type=NodeType.FUNCTION,
        name="login",
        file_path="auth.py",
        parent_id=file_node.id,
    )

    store.add_node(file_node)
    store.add_node(class_node)
    store.add_node(func_node)

    # Edge: FILE CONTAINS CLASS
    store.add_edge(GraphEdge(
        source_id=file_node.id,
        target_id=class_node.id,
        edge_type=EdgeType.CONTAINS,
        file_path="auth.py",
    ))
    # Edge: FILE DEFINES FUNCTION
    store.add_edge(GraphEdge(
        source_id=file_node.id,
        target_id=func_node.id,
        edge_type=EdgeType.DEFINES,
        file_path="auth.py",
    ))

    # Test lookups
    assert store.get_node("auth.py") is None
    assert store.get_node(file_node.id) == file_node
    assert len(store.get_nodes(NodeType.CLASS)) == 1
    assert len(store.get_nodes(NodeType.FUNCTION)) == 1

    # Outgoing / Incoming
    outgoing = store.get_outgoing_edges(file_node.id)
    assert len(outgoing) == 2

    contains_edges = store.get_outgoing_edges(file_node.id, edge_type=EdgeType.CONTAINS)
    assert len(contains_edges) == 1
    assert contains_edges[0].target_id == class_node.id

    incoming = store.get_incoming_edges(class_node.id)
    assert len(incoming) == 1
    assert incoming[0].source_id == file_node.id

    # Neighbors
    neighbors = store.get_neighbors(file_node.id)
    neighbor_ids = {n.id for n in neighbors}
    assert class_node.id in neighbor_ids
    assert func_node.id in neighbor_ids

    # Nodes in file
    in_file = store.get_nodes_in_file("auth.py")
    assert len(in_file) == 3


def test_store_json_roundtrip():
    store = GraphStore(metadata={"project": "DevPilot", "files_processed": 5})

    node = GraphNode(
        id="function:api.py:handler",
        node_type=NodeType.FUNCTION,
        name="handler",
        file_path="api.py",
        start_line=1,
        end_line=10,
    )
    store.add_node(node)

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "graph.json"
        store.save(json_path)
        assert json_path.is_file()

        loaded = GraphStore.load(json_path)
        assert loaded.metadata.get("project") == "DevPilot"
        assert loaded.metadata.get("files_processed") == 5
        assert len(loaded.get_nodes()) == 1
        assert loaded.get_node("function:api.py:handler").name == "handler"


def test_store_clear():
    store = GraphStore()
    store.add_node(GraphNode(id="file:a.py", node_type=NodeType.FILE, name="a.py", file_path="a.py"))
    assert len(store.get_nodes()) == 1

    store.clear()
    assert len(store.get_nodes()) == 0
    assert len(store.get_edges()) == 0
