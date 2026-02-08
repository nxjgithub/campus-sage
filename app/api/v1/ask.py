"""问答相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_rag_service
from app.api.v1.mappers import rag_result_to_response
from app.api.v1.schemas.rag import AskRequest, AskResponse
from app.rag.service import RagService

router = APIRouter(tags=["RAG"])


@router.post("/kb/{kb_id}/ask", response_model=AskResponse)
def ask_question(
    request: Request,
    kb_id: str,
    payload: AskRequest,
    service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """基于知识库进行问答。"""

    filters = payload.filters.model_dump() if payload.filters else None
    result = service.ask(
        kb_id=kb_id,
        question=payload.question,
        request_id=request.state.request_id,
        conversation_id=payload.conversation_id,
        topk=payload.topk,
        threshold=payload.threshold,
        rerank_enabled=payload.rerank_enabled,
        filters=filters,
        debug=payload.debug,
    )
    return rag_result_to_response(result)
