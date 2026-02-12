"""问答相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import (
    get_authorization_service,
    get_kb_service,
    get_optional_user,
    get_rag_service,
)
from app.api.v1.mappers import rag_result_to_response
from app.api.v1.schemas.rag import AskRequest, AskResponse
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService
from app.rag.service import RagService

router = APIRouter(tags=["RAG"])


@router.post("/kb/{kb_id}/ask", response_model=AskResponse)
def ask_question(
    request: Request,
    kb_id: str,
    payload: AskRequest,
    current_user: CurrentUser | None = Depends(get_optional_user),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """基于知识库进行问答。"""

    kb_record = kb_service.get(kb_id)
    if current_user is not None:
        if Permission.RAG_ASK not in current_user.permissions and "*" not in current_user.permissions:
            raise AppError(
                code=ErrorCode.AUTH_FORBIDDEN,
                message="权限不足",
                detail={"permission": Permission.RAG_ASK},
                status_code=403,
            )
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=True,
    )
    filters = payload.filters.model_dump() if payload.filters else None
    result = service.ask(
        kb_id=kb_id,
        question=payload.question,
        request_id=request.state.request_id,
        conversation_id=payload.conversation_id,
        user_id=current_user.user.user_id if current_user else None,
        topk=payload.topk,
        threshold=payload.threshold,
        rerank_enabled=payload.rerank_enabled,
        filters=filters,
        debug=payload.debug,
    )
    return rag_result_to_response(result)
