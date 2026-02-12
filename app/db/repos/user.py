"""用户仓库实现（SQLite）。"""

from __future__ import annotations

from app.core.utils import utc_now_iso
from app.db.database import Database
from app.db.models import RoleRecord, UserRecord


class UserRepository:
    """用户仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: UserRecord) -> UserRecord:
        """创建用户记录。"""

        self._db.execute(
            """
            INSERT INTO user (
                user_id, email, password_hash, status, created_at, updated_at, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.user_id,
                record.email,
                record.password_hash,
                record.status,
                record.created_at,
                record.updated_at,
                record.last_login_at,
            ),
        )
        return record

    def get(self, user_id: str) -> UserRecord | None:
        """获取用户。"""

        row = self._db.fetch_one(
            """
            SELECT user_id, email, password_hash, status, created_at, updated_at, last_login_at
            FROM user WHERE user_id = ?;
            """,
            (user_id,),
        )
        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_email(self, email: str) -> UserRecord | None:
        """通过邮箱获取用户。"""

        row = self._db.fetch_one(
            """
            SELECT user_id, email, password_hash, status, created_at, updated_at, last_login_at
            FROM user WHERE email = ?;
            """,
            (email,),
        )
        if row is None:
            return None
        return self._row_to_record(row)

    def list_all(self) -> list[UserRecord]:
        """列出用户。"""

        rows = self._db.fetch_all(
            """
            SELECT user_id, email, password_hash, status, created_at, updated_at, last_login_at
            FROM user
            WHERE status != 'deleted'
            ORDER BY created_at DESC;
            """
        )
        return [self._row_to_record(row) for row in rows]

    def list_filtered(
        self,
        status: str | None,
        keyword: str | None,
        limit: int,
        offset: int,
    ) -> list[UserRecord]:
        """按条件分页查询用户。"""

        where_clause, params = self._build_filter(status, keyword)
        params.extend([limit, offset])
        rows = self._db.fetch_all(
            f"""
            SELECT user_id, email, password_hash, status, created_at, updated_at, last_login_at
            FROM user
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?;
            """,
            tuple(params),
        )
        return [self._row_to_record(row) for row in rows]

    def count_filtered(self, status: str | None, keyword: str | None) -> int:
        """统计符合条件的用户数量。"""

        where_clause, params = self._build_filter(status, keyword)
        row = self._db.fetch_one(
            f"""
            SELECT COUNT(1) as total
            FROM user
            {where_clause};
            """,
            tuple(params),
        )
        if row is None:
            return 0
        return int(row["total"])

    def update(self, record: UserRecord) -> UserRecord:
        """更新用户记录。"""

        self._db.execute(
            """
            UPDATE user
            SET email = ?, password_hash = ?, status = ?, updated_at = ?, last_login_at = ?
            WHERE user_id = ?;
            """,
            (
                record.email,
                record.password_hash,
                record.status,
                record.updated_at,
                record.last_login_at,
                record.user_id,
            ),
        )
        return record

    def set_roles(self, user_id: str, role_names: list[str]) -> None:
        """设置用户角色。"""

        self._db.execute("DELETE FROM user_role WHERE user_id = ?;", (user_id,))
        if not role_names:
            return
        rows = self._db.fetch_all(
            "SELECT role_id, name FROM role WHERE name IN ({})".format(
                ",".join("?" for _ in role_names)
            ),
            tuple(role_names),
        )
        for row in rows:
            self._db.execute(
                """
                INSERT INTO user_role (user_id, role_id, created_at)
                VALUES (?, ?, ?);
                """,
                (user_id, row["role_id"], utc_now_iso()),
            )

    def list_roles(self, user_id: str) -> list[RoleRecord]:
        """列出用户角色。"""

        rows = self._db.fetch_all(
            """
            SELECT r.role_id, r.name, r.permissions_json, r.created_at
            FROM role r
            JOIN user_role ur ON r.role_id = ur.role_id
            WHERE ur.user_id = ?;
            """,
            (user_id,),
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

    @staticmethod
    def _row_to_record(row: dict) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            email=row["email"],
            password_hash=row["password_hash"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )

    @staticmethod
    def _build_filter(
        status: str | None,
        keyword: str | None,
    ) -> tuple[str, list[object]]:
        """构建筛选条件与参数。"""

        params: list[object] = []
        where_parts: list[str] = []
        if status:
            where_parts.append("status = ?")
            params.append(status)
        else:
            where_parts.append("status != 'deleted'")
        if keyword:
            where_parts.append("(email LIKE ? OR user_id LIKE ?)")
            like_value = f"%{keyword}%"
            params.extend([like_value, like_value])
        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        return where_clause, params
