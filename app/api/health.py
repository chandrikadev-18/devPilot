from fastapi import APIRouter
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Returns the health status, service name, and version of DevPilot.",
)
def get_health() -> HealthResponse:
    """Returns service health and version information."""
    return HealthResponse(
        status="ok",
        service="DevPilot",
        version="1.4",
    )
