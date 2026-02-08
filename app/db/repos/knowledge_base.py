"""知识库仓库实现（SQLite）。"""

from __future__ import annotations

import json
import sqlite3

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.db.database import Database
from app.db.models import KnowledgeBaseRecord


class KnowledgeBaseRepository:
    """知识库仓库（SQLite）。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: KnowledgeBaseRecord) -> KnowledgeBaseRecord:
        """创建知识库记录。"""

        try:
            self._db.execute(
                """
                INSERT INTO knowledge_base (
                    kb_id, name, description, visibility, config_json,
                    created_at, updated_at, deleted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.kb_id,
                    record.name,
                    record.description,
                    record.visibility,
                    self._dumps(record.config),
                    record.created_at,
                    record.updated_at,
                    int(record.deleted),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(
                code=ErrorCode.KB_ALREADY_EXISTS,
                message="知识库名称已存在",
                detail={"name": record.name},
                status_code=409,
            ) from exc
        return record

    def get(self, kb_id: str) -> KnowledgeBaseRecord | None:
        """获取知识库记录。"""

        row = self._db.fetch_one(
            """
            SELECT kb_id, name, description, visibility, config_json,
                   created_at, updated_at, deleted
            FROM knowledge_base
            WHERE kb_id = ?;
            """,
            (kb_id,),
        )
        if row is None:
            return None
        return KnowledgeBaseRecord(
            kb_id=row["kb_id"],
            name=row["name"],
            description=row["description"],
            visibility=row["visibility"],
            config=self._loads(row["config_json"]) or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted=bool(row["deleted"]),
        )

    def list_all(self) -> list[KnowledgeBaseRecord]:
        """列出知识库记录。"""

        rows = self._db.fetch_all(
            """
            SELECT kb_id, name, description, visibility, config_json,
                   created_at, updated_at, deleted
            FROM knowledge_base
            WHERE deleted = 0
            ORDER BY updated_at DESC;
            """
        )
        return [
            KnowledgeBaseRecord(
                kb_id=row["kb_id"],
                name=row["name"],
                description=row["description"],
                visibility=row["visibility"],
                config=self._loads(row["config_json"]) or {},
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                deleted=bool(row["deleted"]),
            )
            for row in rows
        ]

    def update(self, record: KnowledgeBaseRecord) -> KnowledgeBaseRecord:
        """更新知识库记录。"""

        self._db.execute(
            """
            UPDATE knowledge_base
            SET name = ?, description = ?, visibility = ?, config_json = ?,
                updated_at = ?, deleted = ?
            WHERE kb_id = ?;
            """,
            (
                record.name,
                record.description,
                record.visibility,
                self._dumps(record.config),
                record.updated_at,
                int(record.deleted),
                record.kb_id,
            ),
        )
        return record

    @staticmethod
    def _dumps(payload: object | None) -> str:
        """序列化 JSON。"""

        if payload is None:
            return "{}"
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _loads(payload: str | None) -> object | None:
        """反序列化 JSON。"""

        if not payload:
            return None
        return json.loads(payload)
