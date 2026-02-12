"""评测结果仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import EvalResultRecord


class EvalResultRepository:
    """评测结果仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create_many(self, records: list[EvalResultRecord]) -> None:
        """批量写入评测结果。"""

        for record in records:
            self._db.execute(
                """
                INSERT INTO eval_result (
                    run_result_id, run_id, eval_item_id, hit,
                    rank, retrieve_ms, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.run_result_id,
                    record.run_id,
                    record.eval_item_id,
                    int(record.hit),
                    record.rank,
                    record.retrieve_ms,
                    record.notes,
                    record.created_at,
                ),
            )

    def list_by_run(self, run_id: str) -> list[EvalResultRecord]:
        """按运行ID列出评测结果。"""

        rows = self._db.fetch_all(
            """
            SELECT run_result_id, run_id, eval_item_id, hit,
                   rank, retrieve_ms, notes, created_at
            FROM eval_result
            WHERE run_id = ?
            ORDER BY created_at ASC;
            """,
            (run_id,),
        )
        return [
            EvalResultRecord(
                run_result_id=row["run_result_id"],
                run_id=row["run_id"],
                eval_item_id=row["eval_item_id"],
                hit=bool(row["hit"]),
                rank=row["rank"],
                retrieve_ms=row["retrieve_ms"],
                notes=row["notes"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
