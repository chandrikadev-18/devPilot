from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolExecutionMetadata(BaseModel):
    tool: str = Field(..., description="Tool name executed")
    status: str = Field(default="success", description="Status of execution: success or failed")
    duration_ms: float = Field(default=0.0, description="Duration in milliseconds")


class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question for the AI agent about the codebase")
    project_dir: Optional[str] = Field(None, description="Optional root project directory to analyze")
    provider: Optional[str] = Field(None, description="Optional LLM provider name (e.g. groq, mock)")
    model: Optional[str] = Field(None, description="Optional LLM model name")


class AgentAskResponse(BaseModel):
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="Synthesized answer from DevPilot AI Agent")
    tools_used: List[str] = Field(default_factory=list, description="Names of tools executed during reasoning")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Attributed sources and citations")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata including iterations, status, and tool timings")
    iterations: Optional[int] = Field(None, description="Number of reasoning iterations performed")
    timing: Dict[str, float] = Field(default_factory=dict, description="Execution timing breakdown")
