"""刷新令牌仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import RefreshTokenRecord


class RefreshTokenRepository:
    """刷新令牌仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: RefreshTokenRecord) -> RefreshTokenRecord:
        """创建刷新令牌记录。"""

        self._db.execute(
            """
            INSERT INTO refresh_token (
                token_id, user_id, token_hash, expires_at, revoked, created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.token_id,
                record.user_id,
                record.token_hash,
                record.expires_at,
                int(record.revoked),
                record.created_at,
                record.revoked_at,
            ),
        )
        return record

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        """按哈希获取刷新令牌。"""

        row = self._db.fetch_one(
            """
            SELECT token_id, user_id, token_hash, expires_at, revoked, created_at, revoked_at
            FROM refresh_token
            WHERE token_hash = ?;
            """,
            (token_hash,),
        )
        if row is None:
            return None
        return RefreshTokenRecord(
            token_id=row["token_id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            expires_at=row["expires_at"],
            revoked=bool(row["revoked"]),
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
        )

    def revoke(self, token_id: str, revoked_at: str) -> None:
        """吊销刷新令牌。"""

        self._db.execute(
            """
            UPDATE refresh_token
            SET revoked = 1, revoked_at = ?
            WHERE token_id = ?;
            """,
            (revoked_at, token_id),
        )
