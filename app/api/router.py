from fastapi import APIRouter

from app.api.agent import router as agent_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.search import router as search_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(graph_router)
api_router.include_router(search_router)
api_router.include_router(agent_router)
