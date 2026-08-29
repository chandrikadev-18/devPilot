from pathlib import Path
import shutil
from fastapi import APIRouter
from app.config import get_environment, get_llm_api_key, get_llm_model, get_llm_provider
from app.schemas.health import DetailedHealthResponse, HealthResponse

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


@router.get(
    "/health/details",
    response_model=DetailedHealthResponse,
    summary="Detailed Health Check",
    description="Returns detailed diagnostic health of DevPilot subsystems (Git, storage, graph, LLM).",
)
def get_health_details() -> DetailedHealthResponse:
    """Returns granular subsystem diagnostics."""
    # 1. Git subsystem check
    git_cmd = shutil.which("git")
    git_available = bool(git_cmd)
    git_version = None
    if git_available:
        try:
            import subprocess
            res = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                git_version = res.stdout.strip()
        except Exception:
            pass

    # 2. Storage subsystem check
    storage_ok = True
    storage_writable = True
    try:
        dot_devpilot = Path.cwd() / ".devpilot"
        dot_devpilot.mkdir(parents=True, exist_ok=True)
        test_file = dot_devpilot / ".health_check.tmp"
        test_file.write_text("health", encoding="utf-8")
        if test_file.exists():
            test_file.unlink()
    except Exception:
        storage_writable = False
        storage_ok = False

    # 3. Graph subsystem check
    graph_ok = True
    try:
        from app.graph.builder import GraphBuilder
        _ = GraphBuilder
    except Exception:
        graph_ok = False

    # 4. LLM provider check
    llm_prov = get_llm_provider()
    llm_key_present = bool(get_llm_api_key(llm_prov))

    overall_status = "ok" if (git_available and storage_ok and graph_ok) else "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        service="DevPilot",
        version="1.4",
        environment=get_environment(),
        git={
            "available": git_available,
            "version": git_version or ("available" if git_available else "not_found"),
        },
        storage={
            "available": storage_ok,
            "writable": storage_writable,
        },
        graph={
            "available": graph_ok,
        },
        llm={
            "provider": llm_prov,
            "model": get_llm_model(),
            "api_key_configured": llm_key_present,
        },
    )

