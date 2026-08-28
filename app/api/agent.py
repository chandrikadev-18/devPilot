from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException

from app.agent import create_codebase_agent
from app.embeddings.embedder import CodeEmbedder
from app.llm import (
    LLMAuthenticationError,
    LLMError,
    create_llm_provider,
    strip_thinking_and_tool_tags,
)
from app.schemas.agent import AgentAskRequest, AgentAskResponse
from app.search.semantic_search import SemanticSearcher
from app.vector_store.qdrant_store import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_STORAGE_PATH,
    ConfigurationMismatchError,
    ValidationError,
    VectorStoreError,
    QdrantVectorStore,
)

router = APIRouter(tags=["AI Agent"])


_VECTOR_STORE_CACHE: Dict[str, QdrantVectorStore] = {}
_EMBEDDER_CACHE: Optional[CodeEmbedder] = None


def _get_embedder() -> CodeEmbedder:
    global _EMBEDDER_CACHE
    if _EMBEDDER_CACHE is None:
        _EMBEDDER_CACHE = CodeEmbedder()
    return _EMBEDDER_CACHE


def _get_vector_store(storage_path: str = DEFAULT_STORAGE_PATH) -> QdrantVectorStore:
    resolved = str(Path(storage_path).resolve())
    if resolved not in _VECTOR_STORE_CACHE:
        _VECTOR_STORE_CACHE[resolved] = QdrantVectorStore(storage_path=storage_path)
    return _VECTOR_STORE_CACHE[resolved]


def process_agent_question(req: AgentAskRequest) -> AgentAskResponse:
    """Core logic to process an agent question and build a structured response."""
    question = req.question.strip() if req.question else ""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    root_path = Path(req.project_dir).resolve() if req.project_dir else Path.cwd().resolve()
    if not root_path.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{req.project_dir}'")

    try:
        embedder = _get_embedder()
        store = _get_vector_store(DEFAULT_STORAGE_PATH)
        searcher = SemanticSearcher(
            embedder=embedder,
            vector_store=store,
            collection_name=DEFAULT_COLLECTION_NAME,
        )

        llm = create_llm_provider(
            provider_name=req.provider,
            model=req.model,
        )

        agent = create_codebase_agent(
            llm=llm,
            searcher=searcher,
            project_root=root_path,
            vector_store=store,
            collection_name=DEFAULT_COLLECTION_NAME,
        )

        result = agent.run(question=question)
        answer = strip_thinking_and_tool_tags(result.answer)

        # Extract tools used and tool execution metadata
        tools_used: List[str] = []
        tool_executions: List[Dict[str, Any]] = []

        for tc in result.tool_calls:
            if isinstance(tc, dict):
                t_name = tc.get("tool") or tc.get("name") or str(tc)
                tools_used.append(t_name)
                tool_executions.append({
                    "tool": t_name,
                    "status": tc.get("status", "success"),
                    "duration_ms": tc.get("duration_ms", 0.0),
                })
            else:
                t_name = getattr(tc, "name", str(tc))
                tools_used.append(t_name)
                tool_executions.append({
                    "tool": t_name,
                    "status": "success",
                    "duration_ms": 0.0,
                })

        metadata = {
            "iterations": result.iterations,
            "stopped_reason": result.stopped_reason,
            "timing": result.timing,
            "tool_executions": tool_executions,
        }

        return AgentAskResponse(
            question=question,
            answer=answer,
            tools_used=tools_used,
            sources=result.sources,
            metadata=metadata,
            iterations=result.iterations,
            timing=result.timing,
        )

    except LLMAuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="LLM API key is not configured. Please configure the required environment variable.",
        )
    except LLMError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM Error: {str(e)}",
        )
    except (VectorStoreError, ConfigurationMismatchError, ValidationError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Vector store error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing agent reasoning: {str(e)}",
        )


@router.post(
    "/agent/ask",
    response_model=AgentAskResponse,
    summary="Ask AI Agent a Codebase Question (Agent Namespace)",
    description="Executes DevPilot multi-step reasoning AI Agent with codebase tools to answer questions.",
)
def ask_agent_namespaced(req: AgentAskRequest) -> AgentAskResponse:
    return process_agent_question(req)


@router.post(
    "/ask",
    response_model=AgentAskResponse,
    summary="Ask AI Agent a Codebase Question",
    description="Executes DevPilot multi-step reasoning AI Agent with codebase tools to answer questions.",
)
def ask_agent_root(req: AgentAskRequest) -> AgentAskResponse:
    return process_agent_question(req)


@router.post(
    "/agent/execute",
    response_model=AgentAskResponse,
    summary="Execute AI Agent on Codebase",
    description="Executes DevPilot multi-step reasoning AI Agent with codebase tools to answer questions.",
)
def execute_agent(req: AgentAskRequest) -> AgentAskResponse:
    return process_agent_question(req)
