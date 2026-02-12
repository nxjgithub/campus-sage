from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.utils import new_id, utc_now_iso
from app.db.repos.interfaces import ConversationRepositoryProtocol
from app.db.models import ConversationRecord, MessageRecord


class ConversationService:
    """会话管理服务（SQLite 实现）。"""

    def __init__(self, repository: ConversationRepositoryProtocol) -> None:
        self._repository = repository

    def ensure_conversation(
        self,
        kb_id: str,
        conversation_id: str | None,
        title: str | None,
        user_id: str | None,
    ) -> ConversationRecord:
        """获取或创建会话。"""

        conv_id = conversation_id or new_id("conv")
        record = self._repository.get_conversation(conv_id)
        if record is None:
            now = utc_now_iso()
            record = ConversationRecord(
                conversation_id=conv_id,
                kb_id=kb_id,
                user_id=user_id,
                title=title,
                created_at=now,
                updated_at=now,
                deleted=False,
            )
            return self._repository.create_conversation(record)
        if record.kb_id != kb_id:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="会话不属于当前知识库",
                detail={"conversation_id": conv_id, "kb_id": kb_id},
                status_code=400,
            )
        if record.user_id != user_id:
            raise AppError(
                code=ErrorCode.AUTH_FORBIDDEN,
                message="无权访问该会话",
                detail={"conversation_id": conv_id},
                status_code=403,
            )
        record.updated_at = utc_now_iso()
        if title and not record.title:
            record.title = title
        return self._repository.update_conversation(record)

    def list_conversations(
        self, kb_id: str | None, user_id: str | None, limit: int, offset: int
    ) -> list[ConversationRecord]:
        """列出会话列表。"""

        return self._repository.list_conversations(
            kb_id=kb_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    def get_conversation(self, conversation_id: str) -> ConversationRecord:
        """获取会话。"""

        record = self._repository.get_conversation(conversation_id)
        if record is None or record.deleted:
            raise AppError(
                code=ErrorCode.CONVERSATION_NOT_FOUND,
                message="会话不存在",
                detail={"conversation_id": conversation_id},
                status_code=404,
            )
        return record

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        """列出会话消息。"""

        return self._repository.list_messages(conversation_id)

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        refusal: bool,
        refusal_reason: str | None,
        timing: dict[str, int] | None,
        citations: list[dict[str, object]] | None,
        message_id: str | None = None,
    ) -> MessageRecord:
        """保存消息记录。"""

        msg_id = message_id or new_id("msg")
        record = MessageRecord(
            message_id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            refusal=refusal,
            refusal_reason=refusal_reason,
            timing=timing,
            citations=citations or [],
            created_at=utc_now_iso(),
        )
        return self._repository.create_message(record)

    def get_message(self, message_id: str) -> MessageRecord:
        """获取消息。"""

        record = self._repository.get_message(message_id)
        if record is None:
            raise AppError(
                code=ErrorCode.MESSAGE_NOT_FOUND,
                message="消息不存在",
                detail={"message_id": message_id},
                status_code=404,
            )
        return record
