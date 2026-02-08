from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_conversation_service
from app.api.v1.mappers import conversation_to_list_item, message_to_item
from app.api.v1.schemas.conversations import (
    ConversationDetailResponse,
    ConversationListResponse,
)
from app.rag.conversation_service import ConversationService

router = APIRouter(tags=["Conversations"])


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    kb_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """获取会话列表。"""

    items = service.list_conversations(kb_id=kb_id, limit=limit, offset=offset)
    return ConversationListResponse(
        items=[conversation_to_list_item(item) for item in items],
        request_id=request.state.request_id,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    request: Request,
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetailResponse:
    """获取会话详情（含消息）。"""

    record = service.get_conversation(conversation_id)
    messages = service.list_messages(conversation_id)
    return ConversationDetailResponse(
        conversation_id=record.conversation_id,
        kb_id=record.kb_id,
        messages=[message_to_item(item) for item in messages],
        request_id=request.state.request_id,
    )
