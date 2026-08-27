from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service status")
    service: str = Field(default="DevPilot", description="Service name")
    version: str = Field(default="1.4", description="API version")
