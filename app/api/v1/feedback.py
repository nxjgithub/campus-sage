from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import (
    get_authorization_service,
    get_conversation_service,
    get_feedback_service,
    get_kb_service,
    require_permission,
)
from app.api.v1.schemas.feedback import FeedbackCreateRequest, FeedbackResponse
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService
from app.rag.conversation_service import ConversationService
from app.rag.feedback_service import FeedbackService

router = APIRouter(tags=["Feedback"])


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
def create_feedback(
    request: Request,
    message_id: str,
    payload: FeedbackCreateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.FEEDBACK_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    conversation_service: ConversationService = Depends(get_conversation_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """提交对某条消息的反馈。"""

    message = conversation_service.get_message(message_id)
    conversation = conversation_service.get_conversation(message.conversation_id)
    if "*" not in current_user.permissions and conversation.user_id != current_user.user.user_id:
        raise AppError(
            code=ErrorCode.AUTH_FORBIDDEN,
            message="无权访问该会话",
            detail={"conversation_id": conversation.conversation_id},
            status_code=403,
        )
    kb_record = kb_service.get(conversation.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    record = service.create_feedback(
        message_id=message_id,
        rating=payload.rating,
        reasons=payload.reasons,
        comment=payload.comment,
        expected_hint=payload.expected_hint,
    )
    return FeedbackResponse(
        feedback_id=record.feedback_id,
        message_id=record.message_id,
        status=record.status,
        request_id=request.state.request_id,
    )
