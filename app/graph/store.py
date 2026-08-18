"""
DevPilot Graph Store.

Provides an in-memory graph repository with fast indexed lookups
by ID, symbol name, source/target edge traversals, and JSON persistence.
"""

from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType, normalize_graph_path


class GraphStore:
    """
    In-memory graph database storing code nodes and directed relationship edges.
    """

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._outgoing: Dict[str, List[GraphEdge]] = defaultdict(list)
        self._incoming: Dict[str, List[GraphEdge]] = defaultdict(list)
        self._nodes_by_name: Dict[str, List[str]] = defaultdict(list)
        self._nodes_by_file: Dict[str, List[str]] = defaultdict(list)
        self._edge_keys: Set[tuple] = set()
        self.metadata: Dict[str, Any] = metadata if metadata is not None else {}

    def add_node(self, node: GraphNode) -> None:
        """Adds or updates a node in the graph."""
        if not isinstance(node, GraphNode):
            raise TypeError(f"Expected GraphNode, got {type(node).__name__}")
        
        self._nodes[node.id] = node
        if node.name:
            if node.id not in self._nodes_by_name[node.name]:
                self._nodes_by_name[node.name].append(node.id)
            if node.name.lower() != node.name:
                if node.id not in self._nodes_by_name[node.name.lower()]:
                    self._nodes_by_name[node.name.lower()].append(node.id)

        if node.file_path:
            norm_f = normalize_graph_path(node.file_path)
            if node.id not in self._nodes_by_file[norm_f]:
                self._nodes_by_file[norm_f].append(node.id)

    def add_edge(self, edge: GraphEdge) -> None:
        """Adds a relationship edge if not already present."""
        if not isinstance(edge, GraphEdge):
            raise TypeError(f"Expected GraphEdge, got {type(edge).__name__}")

        key = (edge.source_id, edge.target_id, edge.edge_type)
        if key in self._edge_keys:
            return

        self._edge_keys.add(key)
        self._edges.append(edge)
        self._outgoing[edge.source_id].append(edge)
        self._incoming[edge.target_id].append(edge)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieves a node by exact ID."""
        return self._nodes.get(node_id)

    def get_nodes(self, node_type: Optional[NodeType] = None) -> List[GraphNode]:
        """Returns all nodes, optionally filtered by node_type."""
        if node_type is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def get_edges(self, edge_type: Optional[EdgeType] = None) -> List[GraphEdge]:
        """Returns all edges, optionally filtered by edge_type."""
        if edge_type is None:
            return list(self._edges)
        return [e for e in self._edges if e.edge_type == edge_type]

    def get_outgoing_edges(self, node_id: str, edge_type: Optional[EdgeType] = None) -> List[GraphEdge]:
        """Returns edges originating from node_id."""
        edges = self._outgoing.get(node_id, [])
        if edge_type is None:
            return list(edges)
        return [e for e in edges if e.edge_type == edge_type]

    def get_incoming_edges(self, node_id: str, edge_type: Optional[EdgeType] = None) -> List[GraphEdge]:
        """Returns edges targeting node_id."""
        edges = self._incoming.get(node_id, [])
        if edge_type is None:
            return list(edges)
        return [e for e in edges if e.edge_type == edge_type]

    def get_neighbors(self, node_id: str) -> List[GraphNode]:
        """Returns all adjacent target nodes reached from node_id."""
        target_ids = {e.target_id for e in self._outgoing.get(node_id, [])}
        return [self._nodes[tid] for tid in target_ids if tid in self._nodes]

    def find_nodes_by_name(self, name: str) -> List[GraphNode]:
        """Finds nodes matching symbol name (case-sensitive, fallback case-insensitive)."""
        target = name.strip()
        ids = self._nodes_by_name.get(target, [])
        if not ids:
            ids = self._nodes_by_name.get(target.lower(), [])
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def get_nodes_in_file(self, file_path: str) -> List[GraphNode]:
        """Returns all nodes defined within a file."""
        norm_f = normalize_graph_path(file_path)
        ids = self._nodes_by_file.get(norm_f, [])
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def clear(self) -> None:
        """Clears all nodes, edges, and indices."""
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._nodes_by_name.clear()
        self._nodes_by_file.clear()
        self._edge_keys.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes graph to a dictionary."""
        return {
            "version": "1.0",
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "metadata": self.metadata,
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphStore":
        """Deserializes graph from a dictionary."""
        store = cls(metadata=data.get("metadata", {}))
        for node_data in data.get("nodes", []):
            store.add_node(GraphNode.from_dict(node_data))
        for edge_data in data.get("edges", []):
            store.add_edge(GraphEdge.from_dict(edge_data))
        return store

    def save(self, file_path: str | Path) -> None:
        """Saves graph to a JSON file."""
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, file_path: str | Path) -> "GraphStore":
        """Loads graph from a JSON file."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Graph file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def save_graph(graph: GraphStore, file_path: str | Path) -> None:
    """Helper to save graph to disk."""
    graph.save(file_path)


def load_graph(file_path: str | Path) -> GraphStore:
    """Helper to load graph from disk."""
    return GraphStore.load(file_path)
