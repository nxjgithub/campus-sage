from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_authorization_service, get_conversation_service, get_kb_service, require_permission
from app.api.v1.mappers import conversation_to_list_item, message_to_item
from app.api.v1.schemas.conversations import (
    ConversationDetailResponse,
    ConversationListResponse,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService
from app.rag.conversation_service import ConversationService

router = APIRouter(tags=["Conversations"])


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    kb_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """获取会话列表。"""

    items = []
    user_filter = None if "*" in current_user.permissions else current_user.user.user_id
    records = service.list_conversations(
        kb_id=kb_id,
        user_id=user_filter,
        limit=limit,
        offset=offset,
    )
    for record in records:
        try:
            kb_record = kb_service.get(record.kb_id)
            authz.ensure_kb_access(
                current_user=current_user,
                kb_id=record.kb_id,
                visibility=kb_record.visibility,
                required_level="read",
                allow_public=False,
            )
        except AppError:
            continue
        items.append(record)
    return ConversationListResponse(
        items=[conversation_to_list_item(item) for item in items],
        request_id=request.state.request_id,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    request: Request,
    conversation_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetailResponse:
    """获取会话详情（含消息）。"""

    record = service.get_conversation(conversation_id)
    if "*" not in current_user.permissions and record.user_id != current_user.user.user_id:
        raise AppError(
            code=ErrorCode.AUTH_FORBIDDEN,
            message="无权访问该会话",
            detail={"conversation_id": conversation_id},
            status_code=403,
        )
    kb_record = kb_service.get(record.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    messages = service.list_messages(conversation_id)
    return ConversationDetailResponse(
        conversation_id=record.conversation_id,
        kb_id=record.kb_id,
        messages=[message_to_item(item) for item in messages],
        request_id=request.state.request_id,
    )
