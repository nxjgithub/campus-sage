from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import (
    get_authorization_service,
    get_conversation_service,
    get_kb_service,
    require_permission,
)
from app.api.v1.mappers import conversation_to_list_item, message_to_item
from app.api.v1.schemas.conversations import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDeleteResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationRenameRequest,
    MessagePageResponse,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService
from app.rag.conversation_service import ConversationService

router = APIRouter(tags=["Conversations"])


@router.post("/conversations", response_model=ConversationCreateResponse)
def create_conversation(
    request: Request,
    payload: ConversationCreateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationCreateResponse:
    """创建空会话。"""

    kb_record = kb_service.get(payload.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=payload.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    record = service.create_conversation(
        kb_id=payload.kb_id,
        user_id=current_user.user.user_id,
        title=payload.title,
    )
    return ConversationCreateResponse(
        conversation_id=record.conversation_id,
        kb_id=record.kb_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
        request_id=request.state.request_id,
    )


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    kb_id: str | None = None,
    keyword: str | None = None,
    cursor: str | None = None,
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
    result = service.list_conversations(
        kb_id=kb_id,
        user_id=user_filter,
        keyword=keyword,
        cursor=cursor,
        limit=max(1, min(100, limit)),
        offset=max(0, offset),
    )
    for record in result.items:
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
    total = result.total if len(items) == len(result.items) else len(items)
    next_cursor = result.next_cursor if len(items) == len(result.items) else None
    return ConversationListResponse(
        items=[conversation_to_list_item(item) for item in items],
        total=total,
        next_cursor=next_cursor,
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
    _ensure_conversation_owner(current_user, record.user_id, conversation_id)
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


@router.patch("/conversations/{conversation_id}", response_model=ConversationCreateResponse)
def rename_conversation(
    request: Request,
    conversation_id: str,
    payload: ConversationRenameRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationCreateResponse:
    """重命名会话。"""

    record = service.get_conversation(conversation_id)
    _ensure_conversation_owner(current_user, record.user_id, conversation_id)
    kb_record = kb_service.get(record.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    updated = service.rename_conversation(conversation_id, payload.title)
    return ConversationCreateResponse(
        conversation_id=updated.conversation_id,
        kb_id=updated.kb_id,
        title=updated.title,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        request_id=request.state.request_id,
    )


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteResponse)
def delete_conversation(
    request: Request,
    conversation_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDeleteResponse:
    """软删除会话。"""

    record = service.get_conversation(conversation_id)
    _ensure_conversation_owner(current_user, record.user_id, conversation_id)
    kb_record = kb_service.get(record.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    service.delete_conversation(conversation_id)
    return ConversationDeleteResponse(
        conversation_id=conversation_id,
        status="deleted",
        request_id=request.state.request_id,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePageResponse)
def list_conversation_messages(
    request: Request,
    conversation_id: str,
    before: str | None = None,
    limit: int = 50,
    current_user: CurrentUser = Depends(require_permission(Permission.CONVERSATION_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: ConversationService = Depends(get_conversation_service),
) -> MessagePageResponse:
    """分页获取会话消息。"""

    record = service.get_conversation(conversation_id)
    _ensure_conversation_owner(current_user, record.user_id, conversation_id)
    kb_record = kb_service.get(record.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    page = service.list_messages_page(
        conversation_id=conversation_id,
        before_message_id=before,
        limit=min(100, max(1, limit)),
    )
    return MessagePageResponse(
        items=[message_to_item(item) for item in page.items],
        has_more=page.has_more,
        next_before=page.next_before,
        request_id=request.state.request_id,
    )


def _ensure_conversation_owner(
    current_user: CurrentUser,
    conversation_user_id: str | None,
    conversation_id: str,
) -> None:
    """校验会话归属。"""

    if "*" in current_user.permissions:
        return
    if conversation_user_id != current_user.user.user_id:
        raise AppError(
            code=ErrorCode.AUTH_FORBIDDEN,
            message="无权访问该会话",
            detail={"conversation_id": conversation_id},
            status_code=403,
        )
