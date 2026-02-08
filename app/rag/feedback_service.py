from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.utils import new_id, utc_now_iso
from app.db.repos.interfaces import ConversationRepositoryProtocol
from app.db.models import FeedbackRecord


class FeedbackService:
    """反馈管理服务（SQLite 实现）。"""

    def __init__(self, repository: ConversationRepositoryProtocol) -> None:
        self._repository = repository

    def create_feedback(
        self,
        message_id: str,
        rating: str,
        reasons: list[str],
        comment: str | None,
        expected_hint: str | None,
    ) -> FeedbackRecord:
        """创建反馈。"""

        message = self._repository.get_message(message_id)
        if message is None:
            raise AppError(
                code=ErrorCode.MESSAGE_NOT_FOUND,
                message="消息不存在",
                detail={"message_id": message_id},
                status_code=404,
            )

        feedback_id = new_id("fb")
        record = FeedbackRecord(
            feedback_id=feedback_id,
            message_id=message_id,
            rating=rating,
            reasons=reasons,
            comment=comment,
            expected_hint=expected_hint,
            status="received",
            created_at=utc_now_iso(),
        )
        return self._repository.create_feedback(record)
