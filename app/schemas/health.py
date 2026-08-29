from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service status")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="API version")


class DetailedHealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall health status (ok, degraded, error)")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="API version")
    environment: str = Field(default="development", description="Deployment environment")
    git: Dict[str, Any] = Field(default_factory=dict, description="Git subsystem status")
    storage: Dict[str, Any] = Field(default_factory=dict, description="Storage subsystem status")
    graph: Dict[str, Any] = Field(default_factory=dict, description="Graph subsystem status")
    llm: Dict[str, Any] = Field(default_factory=dict, description="LLM provider configuration status")

