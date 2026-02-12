"""会话与消息仓库实现（SQLite）。"""

from __future__ import annotations

import json

from app.db.database import Database
from app.core.utils import new_id, utc_now_iso
from app.db.models import CitationRecord, ConversationRecord, FeedbackRecord, MessageRecord


class ConversationRepository:
    """会话与消息仓库（SQLite）。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        """获取会话记录。"""

        row = self._db.fetch_one(
            """
            SELECT conversation_id, kb_id, user_id, title, created_at, updated_at, deleted
            FROM conversation
            WHERE conversation_id = ? AND deleted = 0;
            """,
            (conversation_id,),
        )
        if row is None:
            return None
        return ConversationRecord(
            conversation_id=row["conversation_id"],
            kb_id=row["kb_id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted=bool(row["deleted"]),
        )

    def create_conversation(self, record: ConversationRecord) -> ConversationRecord:
        """创建会话记录。"""

        self._db.execute(
            """
            INSERT INTO conversation (
                conversation_id, kb_id, user_id, title, created_at, updated_at, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.conversation_id,
                record.kb_id,
                record.user_id,
                record.title,
                record.created_at,
                record.updated_at,
                int(record.deleted),
            ),
        )
        return record

    def update_conversation(self, record: ConversationRecord) -> ConversationRecord:
        """更新会话记录。"""

        self._db.execute(
            """
            UPDATE conversation
            SET title = ?, updated_at = ?, deleted = ?, user_id = ?
            WHERE conversation_id = ?;
            """,
            (
                record.title,
                record.updated_at,
                int(record.deleted),
                record.user_id,
                record.conversation_id,
            ),
        )
        return record

    def list_conversations(
        self, kb_id: str | None, user_id: str | None, limit: int, offset: int
    ) -> list[ConversationRecord]:
        """查询会话列表。"""

        params: list[object] = []
        where_clause = "WHERE deleted = 0"
        if kb_id:
            where_clause += " AND kb_id = ?"
            params.append(kb_id)
        if user_id:
            where_clause += " AND user_id = ?"
            params.append(user_id)
        params.extend([limit, offset])
        rows = self._db.fetch_all(
            f"""
            SELECT conversation_id, kb_id, user_id, title, created_at, updated_at, deleted
            FROM conversation
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?;
            """,
            tuple(params),
        )
        return [
            ConversationRecord(
                conversation_id=row["conversation_id"],
                kb_id=row["kb_id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                deleted=bool(row["deleted"]),
            )
            for row in rows
        ]

    def create_message(self, record: MessageRecord) -> MessageRecord:
        """创建消息记录。"""

        self._db.execute(
            """
            INSERT INTO message (
                message_id, conversation_id, role, content, refusal, refusal_reason,
                timing_json, citations_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.message_id,
                record.conversation_id,
                record.role,
                record.content,
                int(record.refusal),
                record.refusal_reason,
                self._dumps(record.timing),
                self._dumps(record.citations),
                record.created_at,
            ),
        )
        if record.citations:
            self._insert_citations(record.message_id, record.citations)
        return record

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        """查询会话消息。"""

        rows = self._db.fetch_all(
            """
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, citations_json, created_at
            FROM message
            WHERE conversation_id = ?
            ORDER BY created_at ASC;
            """,
            (conversation_id,),
        )
        return [
            MessageRecord(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                refusal=bool(row["refusal"]),
                refusal_reason=row["refusal_reason"],
                timing=self._loads(row["timing_json"]),
                citations=self._loads(row["citations_json"]) or [],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_message(self, message_id: str) -> MessageRecord | None:
        """获取单条消息。"""

        row = self._db.fetch_one(
            """
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, citations_json, created_at
            FROM message
            WHERE message_id = ?;
            """,
            (message_id,),
        )
        if row is None:
            return None
        return MessageRecord(
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            refusal=bool(row["refusal"]),
            refusal_reason=row["refusal_reason"],
            timing=self._loads(row["timing_json"]),
            citations=self._loads(row["citations_json"]) or [],
            created_at=row["created_at"],
        )

    def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord:
        """创建反馈记录。"""

        self._db.execute(
            """
            INSERT INTO feedback (
                feedback_id, message_id, rating, reasons_json, comment, expected_hint,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.feedback_id,
                record.message_id,
                record.rating,
                self._dumps(record.reasons),
                record.comment,
                record.expected_hint,
                record.status,
                record.created_at,
            ),
        )
        return record

    def _insert_citations(self, message_id: str, citations: list[dict[str, object]]) -> None:
        """批量写入引用记录。"""

        for citation in citations:
            record = CitationRecord(
                citation_row_id=new_id("cit"),
                message_id=message_id,
                citation_id=int(citation.get("citation_id") or 0),
                doc_id=str(citation.get("doc_id") or ""),
                doc_name=str(citation.get("doc_name") or ""),
                doc_version=citation.get("doc_version"),
                published_at=citation.get("published_at"),
                page_start=citation.get("page_start"),
                page_end=citation.get("page_end"),
                section_path=citation.get("section_path"),
                chunk_id=str(citation.get("chunk_id") or ""),
                snippet=str(citation.get("snippet") or ""),
                score=citation.get("score"),
                created_at=utc_now_iso(),
            )
            self._db.execute(
                """
                INSERT INTO citation (
                    citation_row_id, message_id, citation_id, doc_id, doc_name, doc_version,
                    published_at, page_start, page_end, section_path, chunk_id, snippet, score,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.citation_row_id,
                    record.message_id,
                    record.citation_id,
                    record.doc_id,
                    record.doc_name,
                    record.doc_version,
                    record.published_at,
                    record.page_start,
                    record.page_end,
                    record.section_path,
                    record.chunk_id,
                    record.snippet,
                    record.score,
                    record.created_at,
                ),
            )

    @staticmethod
    def _dumps(payload: object | None) -> str | None:
        """序列化 JSON。"""

        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _loads(payload: str | None) -> object | None:
        """反序列化 JSON。"""

        if not payload:
            return None
        return json.loads(payload)
