"""角色仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import RoleRecord


class RoleRepository:
    """角色仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: RoleRecord) -> RoleRecord:
        """创建角色。"""

        self._db.execute(
            """
            INSERT INTO role (role_id, name, permissions_json, created_at)
            VALUES (?, ?, ?, ?);
            """,
            (record.role_id, record.name, record.permissions_json, record.created_at),
        )
        return record

    def get_by_name(self, name: str) -> RoleRecord | None:
        """按名称获取角色。"""

        row = self._db.fetch_one(
            """
            SELECT role_id, name, permissions_json, created_at
            FROM role WHERE name = ?;
            """,
            (name,),
        )
        if row is None:
            return None
        return RoleRecord(
            role_id=row["role_id"],
            name=row["name"],
            permissions_json=row["permissions_json"],
            created_at=row["created_at"],
        )

    def list_all(self) -> list[RoleRecord]:
        """列出角色。"""

        rows = self._db.fetch_all(
            """
            SELECT role_id, name, permissions_json, created_at
            FROM role ORDER BY name ASC;
            """
        )
        return [
            RoleRecord(
                role_id=row["role_id"],
                name=row["name"],
                permissions_json=row["permissions_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
