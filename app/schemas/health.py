from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service status (ok, degraded, unavailable)")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="API version")


class DetailedHealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall health status (ok, degraded, unavailable)")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="API version")
    environment: str = Field(default="development", description="Deployment environment")
    git: Dict[str, Any] = Field(default_factory=dict, description="Git subsystem status")
    storage: Dict[str, Any] = Field(default_factory=dict, description="Storage subsystem status")
    graph: Dict[str, Any] = Field(default_factory=dict, description="Graph subsystem status")
    llm: Dict[str, Any] = Field(default_factory=dict, description="LLM provider configuration status")


class ReadinessResponse(BaseModel):
    status: str = Field(default="healthy", description="Readiness state: healthy, degraded, unavailable")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="Application version")
    checks: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Subsystem readiness checks")
    ready: bool = Field(default=True, description="Whether service is ready to accept traffic")
