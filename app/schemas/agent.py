from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question for the AI agent about the codebase")
    project_dir: Optional[str] = Field(None, description="Optional root project directory to analyze")
    provider: Optional[str] = Field(None, description="Optional LLM provider name (e.g. groq, mock)")
    model: Optional[str] = Field(None, description="Optional LLM model name")


class AgentAskResponse(BaseModel):
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="Synthesized answer from DevPilot AI Agent")
    tools_used: List[str] = Field(default_factory=list, description="Names of tools executed during reasoning")
    iterations: Optional[int] = Field(None, description="Number of reasoning iterations performed")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Attributed sources and citations")
    timing: Dict[str, float] = Field(default_factory=dict, description="Execution timing breakdown")
