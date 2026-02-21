"""聊天运行仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import ChatRunRecord


class ChatRunRepository:
    """聊天运行仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: ChatRunRecord) -> ChatRunRecord:
        """创建运行记录。"""

        self._db.execute(
            """
            INSERT INTO chat_run (
                run_id, kb_id, user_id, conversation_id, user_message_id, assistant_message_id,
                status, cancel_flag, started_at, finished_at, request_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.run_id,
                record.kb_id,
                record.user_id,
                record.conversation_id,
                record.user_message_id,
                record.assistant_message_id,
                record.status,
                int(record.cancel_flag),
                record.started_at,
                record.finished_at,
                record.request_id,
            ),
        )
        return record

    def get(self, run_id: str) -> ChatRunRecord | None:
        """获取运行记录。"""

        row = self._db.fetch_one(
            """
            SELECT run_id, kb_id, user_id, conversation_id, user_message_id, assistant_message_id,
                   status, cancel_flag, started_at, finished_at, request_id
            FROM chat_run
            WHERE run_id = ?;
            """,
            (run_id,),
        )
        if row is None:
            return None
        return ChatRunRecord(
            run_id=row["run_id"],
            kb_id=row["kb_id"],
            user_id=row["user_id"],
            conversation_id=row["conversation_id"],
            user_message_id=row["user_message_id"],
            assistant_message_id=row["assistant_message_id"],
            status=row["status"],
            cancel_flag=bool(row["cancel_flag"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            request_id=row["request_id"],
        )

    def update(self, record: ChatRunRecord) -> ChatRunRecord:
        """更新运行记录。"""

        self._db.execute(
            """
            UPDATE chat_run
            SET kb_id = ?, user_id = ?, conversation_id = ?, user_message_id = ?, assistant_message_id = ?,
                status = ?, cancel_flag = ?, started_at = ?, finished_at = ?, request_id = ?
            WHERE run_id = ?;
            """,
            (
                record.kb_id,
                record.user_id,
                record.conversation_id,
                record.user_message_id,
                record.assistant_message_id,
                record.status,
                int(record.cancel_flag),
                record.started_at,
                record.finished_at,
                record.request_id,
                record.run_id,
            ),
        )
        return record
