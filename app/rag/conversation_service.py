from __future__ import annotations

from dataclasses import dataclass

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.utils import new_id, utc_now_iso
from app.db.repos.interfaces import ConversationRepositoryProtocol
from app.db.models import ConversationRecord, MessageRecord


@dataclass(slots=True)
class ConversationListResult:
    """会话列表查询结果。"""

    items: list[ConversationRecord]
    total: int
    next_cursor: str | None


@dataclass(slots=True)
class MessagePageResult:
    """消息分页查询结果。"""

    items: list[MessageRecord]
    has_more: bool
    next_before: str | None


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

    def create_conversation(
        self,
        kb_id: str,
        user_id: str | None,
        title: str | None = None,
    ) -> ConversationRecord:
        """创建空会话。"""

        now = utc_now_iso()
        record = ConversationRecord(
            conversation_id=new_id("conv"),
            kb_id=kb_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
            deleted=False,
        )
        return self._repository.create_conversation(record)

    def rename_conversation(
        self, conversation_id: str, title: str | None
    ) -> ConversationRecord:
        """重命名会话。"""

        record = self.get_conversation(conversation_id)
        record.title = title
        record.updated_at = utc_now_iso()
        return self._repository.update_conversation(record)

    def delete_conversation(self, conversation_id: str) -> ConversationRecord:
        """软删除会话。"""

        record = self.get_conversation(conversation_id)
        record.deleted = True
        record.updated_at = utc_now_iso()
        return self._repository.update_conversation(record)

    def list_conversations(
        self,
        kb_id: str | None,
        user_id: str | None,
        keyword: str | None,
        cursor: str | None,
        limit: int,
        offset: int,
    ) -> ConversationListResult:
        """列出会话列表。"""

        query_limit = max(1, limit)
        records = self._repository.list_conversations(
            kb_id=kb_id,
            user_id=user_id,
            keyword=keyword,
            cursor=cursor,
            limit=query_limit + 1,
            offset=offset,
        )
        total = self._repository.count_conversations(
            kb_id=kb_id,
            user_id=user_id,
            keyword=keyword,
        )
        has_more = len(records) > query_limit
        records = records[:query_limit]
        next_cursor = None
        if has_more and records:
            tail = records[-1]
            next_cursor = f"{tail.updated_at}|{tail.conversation_id}"
        return ConversationListResult(items=records, total=total, next_cursor=next_cursor)

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

    def list_messages_page(
        self, conversation_id: str, before_message_id: str | None, limit: int
    ) -> MessagePageResult:
        """按游标分页拉取消息。"""

        if before_message_id is not None:
            before = self.get_message(before_message_id)
            if before.conversation_id != conversation_id:
                raise AppError(
                    code=ErrorCode.VALIDATION_FAILED,
                    message="消息游标不属于当前会话",
                    detail={
                        "conversation_id": conversation_id,
                        "before": before_message_id,
                    },
                    status_code=400,
                )
        items, has_more, next_before = self._repository.list_messages_page(
            conversation_id=conversation_id,
            before_message_id=before_message_id,
            limit=max(1, limit),
        )
        return MessagePageResult(items=items, has_more=has_more, next_before=next_before)

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        refusal: bool,
        refusal_reason: str | None,
        timing: dict[str, int] | None,
        suggestions: list[str] | None,
        next_steps: list[dict[str, object]] | None,
        citations: list[dict[str, object]] | None,
        request_id: str | None = None,
        message_id: str | None = None,
        parent_message_id: str | None = None,
        edited_from_message_id: str | None = None,
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
            suggestions=suggestions or [],
            next_steps=next_steps or [],
            citations=citations or [],
            created_at=utc_now_iso(),
            request_id=request_id,
            parent_message_id=parent_message_id,
            edited_from_message_id=edited_from_message_id,
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

    def get_previous_user_message(
        self, conversation_id: str, before_message_id: str
    ) -> MessageRecord | None:
        """获取指定消息之前最近的用户消息。"""

        return self._repository.get_previous_user_message(
            conversation_id=conversation_id,
            before_message_id=before_message_id,
        )
