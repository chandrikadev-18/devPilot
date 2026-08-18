"""
DevPilot Graph Data Models.

Defines the core node, edge, and container models for code dependency
and relationship graphs with deterministic identifier generation.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class NodeType(str, Enum):
    """Supported graph node types."""
    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"


class EdgeType(str, Enum):
    """Supported graph relationship edge types."""
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    BELONGS_TO = "BELONGS_TO"


def normalize_graph_path(file_path: str) -> str:
    """Normalizes file paths to consistent POSIX forward slashes."""
    return Path(file_path).as_posix()


def make_file_node_id(file_path: str) -> str:
    """Generates a deterministic file node ID: 'file:<path>'."""
    return f"file:{normalize_graph_path(file_path)}"


def make_module_node_id(module_name: str) -> str:
    """Generates a deterministic module node ID: 'module:<name>'."""
    return f"module:{module_name.strip()}"


def make_class_node_id(file_path: str, class_name: str) -> str:
    """Generates a deterministic class node ID: 'class:<path>:<class_name>'."""
    return f"class:{normalize_graph_path(file_path)}:{class_name.strip()}"


def make_function_node_id(file_path: str, function_name: str) -> str:
    """Generates a deterministic function node ID: 'function:<path>:<function_name>'."""
    return f"function:{normalize_graph_path(file_path)}:{function_name.strip()}"


def make_method_node_id(file_path: str, class_name: str, method_name: str) -> str:
    """Generates a deterministic method node ID: 'method:<path>:<class_name>.<method_name>'."""
    return f"method:{normalize_graph_path(file_path)}:{class_name.strip()}.{method_name.strip()}"


@dataclass
class GraphNode:
    """
    Represents a code entity node in the dependency graph.
    """
    id: str
    node_type: NodeType
    name: str
    file_path: str
    start_line: int = 0
    end_line: int = 0
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts GraphNode to a serializable dictionary."""
        return {
            "id": self.id,
            "node_type": self.node_type.value if isinstance(self.node_type, NodeType) else str(self.node_type),
            "name": self.name,
            "file_path": normalize_graph_path(self.file_path) if self.file_path else "",
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        """Reconstructs a GraphNode from a dictionary."""
        node_type_val = data.get("node_type", "FILE")
        try:
            node_type = NodeType(node_type_val)
        except ValueError:
            node_type = NodeType.FILE

        return cls(
            id=data["id"],
            node_type=node_type,
            name=data.get("name", ""),
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            parent_id=data.get("parent_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GraphEdge:
    """
    Represents a directed relationship between two code entities.
    """
    source_id: str
    target_id: str
    edge_type: EdgeType
    file_path: str = ""
    line_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts GraphEdge to a serializable dictionary."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value if isinstance(self.edge_type, EdgeType) else str(self.edge_type),
            "file_path": normalize_graph_path(self.file_path) if self.file_path else "",
            "line_number": self.line_number,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        """Reconstructs a GraphEdge from a dictionary."""
        edge_type_val = data.get("edge_type", "CONTAINS")
        try:
            edge_type = EdgeType(edge_type_val)
        except ValueError:
            edge_type = EdgeType.CONTAINS

        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=edge_type,
            file_path=data.get("file_path", ""),
            line_number=data.get("line_number", 0),
            metadata=data.get("metadata", {}),
        )
