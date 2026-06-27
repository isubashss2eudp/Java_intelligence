from __future__ import annotations

"""Chat router: /api/v1/chat

Wraps the existing Phase 3 (RAG) and Phase 7 (multi-agent) pipelines
with per-repository context injection.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.platform.auth import get_current_user
from src.platform.database import get_db
from src.platform.models.user import User
from src.platform.schemas.audit import ChatRequest, ChatResponse
from src.platform.services import assert_can_read, get_repository_or_404

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    response_model=ChatResponse,
    summary="Chat with the AI about a repository",
)
def chat(
    body:         ChatRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> ChatResponse:
    """
    Ask a natural-language question about a repository.

    - If `repository_id` is provided the query is scoped to that repository.
    - If `use_agents` is True the multi-agent pipeline (Phase 7) is used,
      otherwise the standard RAG chain (Phase 3) is used.
    """
    # -- Validate repository access ----------------------------------------
    if body.repository_id:
        repo = get_repository_or_404(db, body.repository_id)
        assert_can_read(db, repo, current_user)
        vectordb_dir = str(Path("data") / "repositories" / str(body.repository_id) / "vectordb")
        collection   = f"repo_{body.repository_id}"
    else:
        # Fallback to the global vectordb (Phases 1-7 default)
        vectordb_dir = "vectordb"
        collection   = "java_repo"

    # -- Build LLM & retriever -----------------------------------------------
    try:
        from src.llm import load_llm
        from src.retriever import build_retriever
        from src.embeddings import load_embeddings

        llm        = load_llm()
        embeddings = load_embeddings()
        retriever  = build_retriever(
            embeddings=embeddings,
            persist_dir=vectordb_dir,
            collection_name=collection,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Intelligence modules unavailable: {exc}",
        )

    # -- Run query -----------------------------------------------------------
    try:
        if body.use_agents:
            from src.agent.graph import run_agent_query

            result = run_agent_query(body.query, llm=llm, retriever=retriever)
            answer     = result.get("answer") or result.get("output", "")
            used_agents = result.get("agents_used", True)
            sources     = result.get("sources", [])
        else:
            from src.rag_chain import run_rag_chain

            result  = run_rag_chain(body.query, llm=llm, retriever=retriever)
            answer  = result.get("answer", "")
            used_agents = False
            sources = [
                doc.metadata.get("source", "")
                for doc in result.get("source_documents", [])
            ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {exc}",
        )

    return ChatResponse(
        answer=answer,
        repository_id=body.repository_id,
        used_agents=used_agents,
        sources=sources,
    )
