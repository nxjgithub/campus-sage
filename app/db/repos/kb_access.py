"""知识库权限仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import KbAccessRecord


class KbAccessRepository:
    """知识库权限仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, user_id: str, kb_id: str) -> KbAccessRecord | None:
        """获取指定权限记录。"""

        row = self._db.fetch_one(
            """
            SELECT user_id, kb_id, access_level, created_at, updated_at
            FROM kb_access
            WHERE user_id = ? AND kb_id = ?;
            """,
            (user_id, kb_id),
        )
        if row is None:
            return None
        return KbAccessRecord(
            user_id=row["user_id"],
            kb_id=row["kb_id"],
            access_level=row["access_level"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert(self, record: KbAccessRecord) -> KbAccessRecord:
        """写入或更新权限记录。"""

        existing = self.get(record.user_id, record.kb_id)
        if existing is None:
            self._db.execute(
                """
                INSERT INTO kb_access (
                    user_id, kb_id, access_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    record.user_id,
                    record.kb_id,
                    record.access_level,
                    record.created_at,
                    record.updated_at,
                ),
            )
            return record
        self._db.execute(
            """
            UPDATE kb_access
            SET access_level = ?, updated_at = ?
            WHERE user_id = ? AND kb_id = ?;
            """,
            (
                record.access_level,
                record.updated_at,
                record.user_id,
                record.kb_id,
            ),
        )
        return record

    def delete(self, user_id: str, kb_id: str) -> bool:
        """删除指定权限记录。"""

        existing = self.get(user_id, kb_id)
        if existing is None:
            return False
        self._db.execute(
            "DELETE FROM kb_access WHERE user_id = ? AND kb_id = ?;",
            (user_id, kb_id),
        )
        return True

    def list_by_user(self, user_id: str) -> list[KbAccessRecord]:
        """列出用户权限。"""

        rows = self._db.fetch_all(
            """
            SELECT user_id, kb_id, access_level, created_at, updated_at
            FROM kb_access
            WHERE user_id = ?
            ORDER BY updated_at DESC;
            """,
            (user_id,),
        )
        return [
            KbAccessRecord(
                user_id=row["user_id"],
                kb_id=row["kb_id"],
                access_level=row["access_level"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def replace_by_user(self, user_id: str, records: list[KbAccessRecord]) -> None:
        """批量替换用户权限。"""

        self._db.execute("DELETE FROM kb_access WHERE user_id = ?;", (user_id,))
        for record in records:
            self._db.execute(
                """
                INSERT INTO kb_access (
                    user_id, kb_id, access_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    record.user_id,
                    record.kb_id,
                    record.access_level,
                    record.created_at,
                    record.updated_at,
                ),
            )
