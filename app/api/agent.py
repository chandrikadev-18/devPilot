from pathlib import Path
from typing import List
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

router = APIRouter(prefix="/agent", tags=["AI Agent"])


@router.post(
    "/ask",
    response_model=AgentAskResponse,
    summary="Ask AI Agent a Codebase Question",
    description="Executes DevPilot multi-step reasoning AI Agent with codebase tools to answer questions.",
)
def ask_agent(req: AgentAskRequest) -> AgentAskResponse:
    question = req.question.strip() if req.question else ""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    root_path = Path(req.project_dir).resolve() if req.project_dir else Path.cwd().resolve()
    if not root_path.exists():
        raise HTTPException(status_code=400, detail=f"Project directory does not exist: '{req.project_dir}'")

    try:
        embedder = CodeEmbedder()
        store = QdrantVectorStore(storage_path=DEFAULT_STORAGE_PATH)
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

        # Extract tools used in order
        tools_used = [
            tc.get("tool") or tc.get("name") or str(tc)
            if isinstance(tc, dict)
            else getattr(tc, "name", str(tc))
            for tc in result.tool_calls
        ]

        return AgentAskResponse(
            question=question,
            answer=answer,
            tools_used=tools_used,
            iterations=result.iterations,
            sources=result.sources,
            timing=result.timing,
        )

    except LLMAuthenticationError as e:
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
