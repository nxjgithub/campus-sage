"""评测样本仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import EvalItemRecord


class EvalItemRepository:
    """评测样本仓库。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create_many(self, records: list[EvalItemRecord]) -> None:
        """批量创建评测样本。"""

        for record in records:
            self._db.execute(
                """
                INSERT INTO eval_item (
                    eval_item_id, eval_set_id, question, gold_doc_id,
                    gold_page_start, gold_page_end, tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.eval_item_id,
                    record.eval_set_id,
                    record.question,
                    record.gold_doc_id,
                    record.gold_page_start,
                    record.gold_page_end,
                    record.tags_json,
                    record.created_at,
                ),
            )

    def list_by_set(self, eval_set_id: str) -> list[EvalItemRecord]:
        """按评测集列出样本。"""

        rows = self._db.fetch_all(
            """
            SELECT eval_item_id, eval_set_id, question, gold_doc_id,
                   gold_page_start, gold_page_end, tags_json, created_at
            FROM eval_item
            WHERE eval_set_id = ?
            ORDER BY created_at ASC;
            """,
            (eval_set_id,),
        )
        return [
            EvalItemRecord(
                eval_item_id=row["eval_item_id"],
                eval_set_id=row["eval_set_id"],
                question=row["question"],
                gold_doc_id=row["gold_doc_id"],
                gold_page_start=row["gold_page_start"],
                gold_page_end=row["gold_page_end"],
                tags_json=row["tags_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
