from fastapi import APIRouter

from app.api.agent import router as agent_router
from app.api.changes import router as changes_router
from app.api.git import router as git_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.search import router as search_router
from app.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(projects_router)
api_router.include_router(git_router)
api_router.include_router(changes_router)
api_router.include_router(graph_router)
api_router.include_router(search_router)
api_router.include_router(agent_router)
api_router.include_router(tasks_router)

