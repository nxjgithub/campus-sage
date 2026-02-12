"""评测集仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import EvalSetRecord


class EvalSetRepository:
    """评测集仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: EvalSetRecord) -> EvalSetRecord:
        """创建评测集记录。"""

        self._db.execute(
            """
            INSERT INTO eval_set (eval_set_id, name, description, created_at)
            VALUES (?, ?, ?, ?);
            """,
            (record.eval_set_id, record.name, record.description, record.created_at),
        )
        return record

    def get(self, eval_set_id: str) -> EvalSetRecord | None:
        """获取评测集记录。"""

        row = self._db.fetch_one(
            """
            SELECT eval_set_id, name, description, created_at
            FROM eval_set
            WHERE eval_set_id = ?;
            """,
            (eval_set_id,),
        )
        if row is None:
            return None
        return EvalSetRecord(
            eval_set_id=row["eval_set_id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )
