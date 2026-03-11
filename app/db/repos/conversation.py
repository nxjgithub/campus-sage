"""会话与消息仓库实现（SQLite）。"""

from __future__ import annotations

import json
from typing import Any

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
            SELECT c.conversation_id, c.kb_id, c.user_id, c.title, c.created_at, c.updated_at, c.deleted,
                   (
                     SELECT substr(m.content, 1, 120)
                     FROM message m
                     WHERE m.conversation_id = c.conversation_id
                     ORDER BY COALESCE(m.sequence_no, 0) DESC, m.created_at DESC
                     LIMIT 1
                   ) AS last_message_preview,
                   (
                     SELECT m.created_at
                     FROM message m
                     WHERE m.conversation_id = c.conversation_id
                     ORDER BY COALESCE(m.sequence_no, 0) DESC, m.created_at DESC
                     LIMIT 1
                   ) AS last_message_at
            FROM conversation c
            WHERE c.conversation_id = ? AND c.deleted = 0;
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
            last_message_preview=row["last_message_preview"],
            last_message_at=row["last_message_at"],
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
        self,
        kb_id: str | None,
        user_id: str | None,
        keyword: str | None,
        cursor: str | None,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        """查询会话列表。"""

        params: list[object] = []
        where_clause = "WHERE c.deleted = 0"
        if kb_id:
            where_clause += " AND c.kb_id = ?"
            params.append(kb_id)
        if user_id:
            where_clause += " AND c.user_id = ?"
            params.append(user_id)
        if keyword:
            where_clause += """
            AND (
                c.title LIKE ?
                OR EXISTS (
                    SELECT 1 FROM message mkw
                    WHERE mkw.conversation_id = c.conversation_id
                    AND mkw.content LIKE ?
                )
            )
            """
            keyword_like = f"%{keyword}%"
            params.extend([keyword_like, keyword_like])
        cursor_updated_at, cursor_conversation_id = self._parse_cursor(cursor)
        if cursor_updated_at is not None and cursor_conversation_id is not None:
            where_clause += " AND (c.updated_at < ? OR (c.updated_at = ? AND c.conversation_id < ?))"
            params.extend([cursor_updated_at, cursor_updated_at, cursor_conversation_id])
        params.extend([limit, offset])
        rows = self._db.fetch_all(
            f"""
            SELECT c.conversation_id, c.kb_id, c.user_id, c.title, c.created_at, c.updated_at, c.deleted,
                   (
                     SELECT substr(m.content, 1, 120)
                     FROM message m
                     WHERE m.conversation_id = c.conversation_id
                     ORDER BY COALESCE(m.sequence_no, 0) DESC, m.created_at DESC
                     LIMIT 1
                   ) AS last_message_preview,
                   (
                     SELECT m.created_at
                     FROM message m
                     WHERE m.conversation_id = c.conversation_id
                     ORDER BY COALESCE(m.sequence_no, 0) DESC, m.created_at DESC
                     LIMIT 1
                   ) AS last_message_at
            FROM conversation c
            {where_clause}
            ORDER BY c.updated_at DESC, c.conversation_id DESC
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
                last_message_preview=row["last_message_preview"],
                last_message_at=row["last_message_at"],
            )
            for row in rows
        ]

    def count_conversations(
        self, kb_id: str | None, user_id: str | None, keyword: str | None
    ) -> int:
        """统计会话数量。"""

        params: list[object] = []
        where_clause = "WHERE c.deleted = 0"
        if kb_id:
            where_clause += " AND c.kb_id = ?"
            params.append(kb_id)
        if user_id:
            where_clause += " AND c.user_id = ?"
            params.append(user_id)
        if keyword:
            where_clause += """
            AND (
                c.title LIKE ?
                OR EXISTS (
                    SELECT 1 FROM message mkw
                    WHERE mkw.conversation_id = c.conversation_id
                    AND mkw.content LIKE ?
                )
            )
            """
            keyword_like = f"%{keyword}%"
            params.extend([keyword_like, keyword_like])
        row = self._db.fetch_one(
            f"""
            SELECT COUNT(1) AS total
            FROM conversation c
            {where_clause};
            """,
            tuple(params),
        )
        if row is None:
            return 0
        return int(row["total"] or 0)

    def create_message(self, record: MessageRecord) -> MessageRecord:
        """创建消息记录。"""

        sequence_no = record.sequence_no or self._next_sequence_no(record.conversation_id)
        record.sequence_no = sequence_no
        self._db.execute(
            """
            INSERT INTO message (
                message_id, conversation_id, role, content, refusal, refusal_reason,
                timing_json, next_steps_json, citations_json, parent_message_id, edited_from_message_id,
                sequence_no, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.message_id,
                record.conversation_id,
                record.role,
                record.content,
                int(record.refusal),
                record.refusal_reason,
                self._dumps(record.timing),
                self._dumps(record.next_steps),
                self._dumps(record.citations),
                record.parent_message_id,
                record.edited_from_message_id,
                record.sequence_no,
                record.created_at,
            ),
        )
        self._db.execute(
            """
            UPDATE conversation
            SET updated_at = ?
            WHERE conversation_id = ?;
            """,
            (record.created_at, record.conversation_id),
        )
        if record.citations:
            self._insert_citations(record.message_id, record.citations)
        return record

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        """查询会话消息。"""

        rows = self._db.fetch_all(
            """
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, next_steps_json, citations_json, parent_message_id, edited_from_message_id,
                   sequence_no, created_at
            FROM message
            WHERE conversation_id = ?
            ORDER BY COALESCE(sequence_no, 0) ASC, created_at ASC;
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
                next_steps=self._loads(row["next_steps_json"]) or [],
                citations=self._loads(row["citations_json"]) or [],
                parent_message_id=row["parent_message_id"],
                edited_from_message_id=row["edited_from_message_id"],
                sequence_no=row["sequence_no"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_messages_page(
        self, conversation_id: str, before_message_id: str | None, limit: int
    ) -> tuple[list[MessageRecord], bool, str | None]:
        """按游标分页查询会话消息。"""

        before_sequence = None
        if before_message_id:
            before_record = self.get_message(before_message_id)
            if before_record is None or before_record.conversation_id != conversation_id:
                return [], False, None
            before_sequence = before_record.sequence_no
        params: list[Any] = [conversation_id]
        where_clause = "WHERE conversation_id = ?"
        if before_sequence is not None:
            where_clause += " AND COALESCE(sequence_no, 0) < ?"
            params.append(before_sequence)
        params.append(limit + 1)
        rows = self._db.fetch_all(
            f"""
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, next_steps_json, citations_json, parent_message_id, edited_from_message_id,
                   sequence_no, created_at
            FROM message
            {where_clause}
            ORDER BY COALESCE(sequence_no, 0) DESC, created_at DESC
            LIMIT ?;
            """,
            tuple(params),
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        rows.reverse()
        items = [
            MessageRecord(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                refusal=bool(row["refusal"]),
                refusal_reason=row["refusal_reason"],
                timing=self._loads(row["timing_json"]),
                next_steps=self._loads(row["next_steps_json"]) or [],
                citations=self._loads(row["citations_json"]) or [],
                parent_message_id=row["parent_message_id"],
                edited_from_message_id=row["edited_from_message_id"],
                sequence_no=row["sequence_no"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        next_before = items[0].message_id if has_more and items else None
        return items, has_more, next_before

    def get_message(self, message_id: str) -> MessageRecord | None:
        """获取单条消息。"""

        row = self._db.fetch_one(
            """
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, next_steps_json, citations_json, parent_message_id, edited_from_message_id,
                   sequence_no, created_at
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
            next_steps=self._loads(row["next_steps_json"]) or [],
            citations=self._loads(row["citations_json"]) or [],
            parent_message_id=row["parent_message_id"],
            edited_from_message_id=row["edited_from_message_id"],
            sequence_no=row["sequence_no"],
            created_at=row["created_at"],
        )

    def get_previous_user_message(
        self, conversation_id: str, before_message_id: str
    ) -> MessageRecord | None:
        """获取指定消息之前最近的一条用户消息。"""

        before = self.get_message(before_message_id)
        if before is None:
            return None
        before_sequence = before.sequence_no or 0
        row = self._db.fetch_one(
            """
            SELECT message_id, conversation_id, role, content, refusal, refusal_reason,
                   timing_json, next_steps_json, citations_json, parent_message_id, edited_from_message_id,
                   sequence_no, created_at
            FROM message
            WHERE conversation_id = ? AND role = 'user' AND COALESCE(sequence_no, 0) < ?
            ORDER BY COALESCE(sequence_no, 0) DESC, created_at DESC
            LIMIT 1;
            """,
            (conversation_id, before_sequence),
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
            next_steps=self._loads(row["next_steps_json"]) or [],
            citations=self._loads(row["citations_json"]) or [],
            parent_message_id=row["parent_message_id"],
            edited_from_message_id=row["edited_from_message_id"],
            sequence_no=row["sequence_no"],
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

    def _next_sequence_no(self, conversation_id: str) -> int:
        """获取会话内下一条消息序号。"""

        row = self._db.fetch_one(
            """
            SELECT MAX(COALESCE(sequence_no, 0)) AS max_sequence_no
            FROM message
            WHERE conversation_id = ?;
            """,
            (conversation_id,),
        )
        max_sequence_no = int((row or {}).get("max_sequence_no") or 0)
        return max_sequence_no + 1

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[str | None, str | None]:
        """解析游标字符串。"""

        if not cursor:
            return None, None
        parts = cursor.split("|", 1)
        if len(parts) != 2:
            return None, None
        updated_at, conversation_id = parts[0].strip(), parts[1].strip()
        if not updated_at or not conversation_id:
            return None, None
        return updated_at, conversation_id
