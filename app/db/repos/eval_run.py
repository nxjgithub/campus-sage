"""评测运行仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import EvalRunRecord


class EvalRunRepository:
    """评测运行仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: EvalRunRecord) -> EvalRunRecord:
        """创建评测运行记录。"""

        self._db.execute(
            """
            INSERT INTO eval_run (
                run_id, eval_set_id, kb_id, topk, threshold, rerank_enabled,
                metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.run_id,
                record.eval_set_id,
                record.kb_id,
                record.topk,
                record.threshold,
                int(record.rerank_enabled),
                record.metrics_json,
                record.created_at,
            ),
        )
        return record

    def get(self, run_id: str) -> EvalRunRecord | None:
        """获取评测运行记录。"""

        row = self._db.fetch_one(
            """
            SELECT run_id, eval_set_id, kb_id, topk, threshold, rerank_enabled,
                   metrics_json, created_at
            FROM eval_run
            WHERE run_id = ?;
            """,
            (run_id,),
        )
        if row is None:
            return None
        return EvalRunRecord(
            run_id=row["run_id"],
            eval_set_id=row["eval_set_id"],
            kb_id=row["kb_id"],
            topk=row["topk"],
            threshold=row["threshold"],
            rerank_enabled=bool(row["rerank_enabled"]),
            metrics_json=row["metrics_json"],
            created_at=row["created_at"],
        )

    def update_metrics(self, run_id: str, metrics_json: str | None) -> None:
        """更新评测运行指标。"""

        self._db.execute(
            "UPDATE eval_run SET metrics_json = ? WHERE run_id = ?;",
            (metrics_json, run_id),
        )
