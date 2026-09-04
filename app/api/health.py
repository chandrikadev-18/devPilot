from pathlib import Path
import shutil
from typing import Any, Dict
from fastapi import APIRouter, Response, status
from app.config import get_environment, get_llm_api_key, get_llm_model, get_llm_provider
from app.observability.metrics import metrics
from app.schemas.health import DetailedHealthResponse, HealthResponse, ReadinessResponse

router = APIRouter(tags=["Health & Observability"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness Probe",
    description="Returns the basic liveness health status of DevPilot.",
)
def get_health() -> HealthResponse:
    """Returns basic service liveness and version information."""
    return HealthResponse(
        status="ok",
        service="DevPilot",
        version="1.4",
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Evaluates critical subsystems (storage, vector database, graph parser, Git) and returns readiness state.",
)
def get_readiness(response: Response) -> ReadinessResponse:
    """
    Comprehensive readiness probe distinguishing healthy, degraded, and unavailable states.
    Returns HTTP 503 if critical persistence storage is unavailable.
    """
    checks: Dict[str, Dict[str, Any]] = {}

    # 1. Storage check (CRITICAL)
    storage_writable = True
    storage_error = None
    try:
        dot_devpilot = Path.cwd() / ".devpilot"
        dot_devpilot.mkdir(parents=True, exist_ok=True)
        test_file = dot_devpilot / ".readiness_probe.tmp"
        test_file.write_text("probe", encoding="utf-8")
        if test_file.exists():
            test_file.unlink()
    except Exception as e:
        storage_writable = False
        storage_error = "Storage directory is not writable"

    checks["storage"] = {
        "status": "healthy" if storage_writable else "unavailable",
        "writable": storage_writable,
        "detail": storage_error or "Filesystem storage ready",
    }

    # 2. Vector store check
    qdrant_ready = True
    qdrant_msg = "Vector store operational"
    try:
        from app.vector_store.qdrant_store import QdrantVectorStore
        _ = QdrantVectorStore
    except Exception as e:
        qdrant_ready = False
        qdrant_msg = "Vector store initialization error"

    checks["vector_store"] = {
        "status": "healthy" if qdrant_ready else "unavailable",
        "detail": qdrant_msg,
    }

    # 3. Graph parser check
    graph_ready = True
    try:
        from app.graph.builder import GraphBuilder
        _ = GraphBuilder
    except Exception:
        graph_ready = False

    checks["graph_parser"] = {
        "status": "healthy" if graph_ready else "degraded",
        "detail": "AST and graph engine ready" if graph_ready else "Graph engine degraded",
    }

    # 4. Git availability check (Optional / Non-critical for standalone exploration)
    git_cmd = shutil.which("git")
    git_available = bool(git_cmd)
    checks["git"] = {
        "status": "healthy" if git_available else "degraded",
        "available": git_available,
        "detail": "Git binary discovered" if git_available else "Git binary not found in PATH",
    }

    # Determine overall status
    if not storage_writable or not qdrant_ready:
        overall_status = "unavailable"
        is_ready = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif not git_available or not graph_ready:
        overall_status = "degraded"
        is_ready = True
    else:
        overall_status = "healthy"
        is_ready = True

    return ReadinessResponse(
        status=overall_status,
        service="DevPilot",
        version="1.4",
        checks=checks,
        ready=is_ready,
    )


@router.get(
    "/health/details",
    response_model=DetailedHealthResponse,
    summary="Detailed Diagnostic Health",
    description="Returns granular subsystem diagnostics.",
)
def get_health_details() -> DetailedHealthResponse:
    """Returns granular subsystem diagnostics."""
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

    graph_ok = True
    try:
        from app.graph.builder import GraphBuilder
        _ = GraphBuilder
    except Exception:
        graph_ok = False

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


@router.get(
    "/metrics",
    summary="Operational Performance Metrics",
    description="Exposes safe in-memory performance metrics, request latency distributions, and task execution counts.",
)
def get_metrics() -> Dict[str, Any]:
    """Returns safe aggregated system performance and operational metrics."""
    return metrics.get_summary()
