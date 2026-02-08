from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_feedback_service
from app.api.v1.schemas.feedback import FeedbackCreateRequest, FeedbackResponse
from app.rag.feedback_service import FeedbackService

router = APIRouter(tags=["Feedback"])


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
def create_feedback(
    request: Request,
    message_id: str,
    payload: FeedbackCreateRequest,
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """提交对某条消息的反馈。"""

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
