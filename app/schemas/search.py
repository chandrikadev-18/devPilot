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
