from typing import List, Optional
from pydantic import BaseModel, Field


class SymbolMatchItem(BaseModel):
    file_path: str = Field(..., description="File path containing the symbol")
    symbol_name: str = Field(..., description="Name of the symbol")
    symbol_type: Optional[str] = Field(None, description="Symbol type (function, method, class)")
    parent_symbol: Optional[str] = Field(None, description="Parent class or container name")
    start_line: Optional[int] = Field(None, description="Starting line number")
    end_line: Optional[int] = Field(None, description="Ending line number")
    code: Optional[str] = Field(None, description="Extracted code snippet")
    chunk_id: Optional[str] = Field(None, description="Associated chunk ID if indexed")


class SymbolSearchResponse(BaseModel):
    query: str = Field(..., description="Search query")
    total_matches: int = Field(..., description="Total matching symbols found")
    matches: List[SymbolMatchItem] = Field(default_factory=list, description="List of matched symbols")


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=50, description="Max results to return")
    project_dir: str = Field(default=".", description="Target project directory")


class SemanticSearchResultItem(BaseModel):
    symbol: str = Field(..., description="Canonical symbol name")
    file: str = Field(..., description="File path containing the symbol")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    score: float = Field(..., description="Hybrid semantic similarity score (0.0-1.0)")
    reason: Optional[str] = Field(None, description="Explanation of semantic relevance")
    symbol_type: Optional[str] = Field(default="function", description="Symbol type (function, method, class)")
    parent_symbol: Optional[str] = Field(None, description="Parent class or container")
    related_symbols: List[str] = Field(default_factory=list, description="Connected symbols in dependency graph")


class SemanticSearchResponse(BaseModel):
    query: str = Field(..., description="Natural language search query")
    total_results: int = Field(..., description="Total semantic matches returned")
    results: List[SemanticSearchResultItem] = Field(default_factory=list, description="Ranked semantic results")

