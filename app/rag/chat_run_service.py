"""聊天运行服务。"""

from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.utils import new_id, utc_now_iso
from app.db.models import ChatRunRecord
from app.db.repos.interfaces import ChatRunRepositoryProtocol


class ChatRunService:
    """聊天运行管理服务。"""

    def __init__(self, repository: ChatRunRepositoryProtocol) -> None:
        self._repository = repository

    def create_run(
        self,
        request_id: str | None,
        kb_id: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> ChatRunRecord:
        """创建运行记录。"""

        record = ChatRunRecord(
            run_id=new_id("run"),
            kb_id=kb_id,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message_id=None,
            assistant_message_id=None,
            status="running",
            cancel_flag=False,
            started_at=utc_now_iso(),
            finished_at=None,
            request_id=request_id,
        )
        return self._repository.create(record)

    def get_run(self, run_id: str) -> ChatRunRecord:
        """获取运行记录。"""

        record = self._repository.get(run_id)
        if record is None:
            raise AppError(
                code=ErrorCode.CHAT_RUN_NOT_FOUND,
                message="聊天运行不存在",
                detail={"run_id": run_id},
                status_code=404,
            )
        return record

    def cancel_run(self, run_id: str) -> ChatRunRecord:
        """取消运行。"""

        record = self.get_run(run_id)
        record.cancel_flag = True
        if record.status == "running":
            record.status = "canceled"
            record.finished_at = utc_now_iso()
        return self._repository.update(record)

    def is_canceled(self, run_id: str) -> bool:
        """判断运行是否已取消。"""

        record = self._repository.get(run_id)
        if record is None:
            return True
        return bool(record.cancel_flag)

    def mark_succeeded(
        self,
        run_id: str,
        conversation_id: str | None,
        user_message_id: str | None,
        assistant_message_id: str | None,
    ) -> ChatRunRecord:
        """标记运行成功。"""

        record = self.get_run(run_id)
        record.conversation_id = conversation_id
        record.user_message_id = user_message_id
        record.assistant_message_id = assistant_message_id
        record.status = "succeeded"
        record.finished_at = utc_now_iso()
        return self._repository.update(record)

    def mark_failed(
        self,
        run_id: str,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
    ) -> ChatRunRecord:
        """标记运行失败。"""

        record = self.get_run(run_id)
        if conversation_id is not None:
            record.conversation_id = conversation_id
        if user_message_id is not None:
            record.user_message_id = user_message_id
        if assistant_message_id is not None:
            record.assistant_message_id = assistant_message_id
        record.status = "failed"
        record.finished_at = utc_now_iso()
        return self._repository.update(record)

    def mark_canceled(
        self,
        run_id: str,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
    ) -> ChatRunRecord:
        """标记运行取消。"""

        record = self.get_run(run_id)
        if conversation_id is not None:
            record.conversation_id = conversation_id
        if user_message_id is not None:
            record.user_message_id = user_message_id
        if assistant_message_id is not None:
            record.assistant_message_id = assistant_message_id
        record.cancel_flag = True
        record.status = "canceled"
        record.finished_at = utc_now_iso()
        return self._repository.update(record)
