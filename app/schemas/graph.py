from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GraphInfoResponse(BaseModel):
    total_nodes: int = Field(..., description="Total nodes in the graph")
    files: int = Field(..., description="Total file nodes")
    classes: int = Field(..., description="Total class nodes")
    functions: int = Field(..., description="Total function nodes")
    methods: int = Field(..., description="Total method nodes")
    modules: int = Field(..., description="Total module nodes")
    total_edges: int = Field(..., description="Total dependency edges")
    calls: int = Field(..., description="CALLS edges")
    imports: int = Field(..., description="IMPORTS edges")
    contains: int = Field(..., description="CONTAINS edges")
    defines: int = Field(..., description="DEFINES edges")
    belongs_to: int = Field(..., description="BELONGS_TO edges")


class CallerItem(BaseModel):
    id: Optional[str] = None
    name: str
    qualified_name: Optional[str] = None
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    call_line: Optional[int] = None
    target_symbol: Optional[str] = None


class CallersResponse(BaseModel):
    symbol: str
    total_callers: int
    callers: List[CallerItem]


class CalleeItem(BaseModel):
    id: Optional[str] = None
    name: str
    qualified_name: Optional[str] = None
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    call_line: Optional[int] = None
    caller_symbol: Optional[str] = None


class CalleesResponse(BaseModel):
    symbol: str
    total_callees: int
    callees: List[CalleeItem]


class DependencyItem(BaseModel):
    id: Optional[str] = None
    name: str
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    call_line: Optional[int] = None
    depth: int
    call_path: Optional[str] = None
    called_by: Optional[str] = None


class DependenciesResponse(BaseModel):
    symbol: str
    depth: int
    total_dependencies: int
    dependencies: List[DependencyItem]


class DependentItem(BaseModel):
    id: Optional[str] = None
    name: str
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    call_line: Optional[int] = None
    depth: int
    dependent_path: Optional[str] = None
    calls_target: Optional[str] = None


class DependentsResponse(BaseModel):
    symbol: str
    depth: int
    total_dependents: int
    dependents: List[DependentItem]


class ImpactItem(BaseModel):
    id: Optional[str] = None
    name: str
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    call_line: Optional[int] = None
    calls_target: Optional[str] = None
    depth: Optional[int] = None


class ImpactResponse(BaseModel):
    symbol: str
    depth: int
    analysis_type: str = Field(default="STATIC DEPENDENCY IMPACT")
    total_impacted: int
    direct_callers: List[ImpactItem] = Field(default_factory=list)
    indirect_callers: List[ImpactItem] = Field(default_factory=list)
    direct_dependents: List[ImpactItem] = Field(default_factory=list)
    indirect_dependents: List[ImpactItem] = Field(default_factory=list)
    impacted_files: List[str] = Field(default_factory=list)
