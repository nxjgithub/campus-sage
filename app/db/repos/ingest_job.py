"""入库任务仓库实现（SQLite）。"""

from __future__ import annotations

import json

from app.db.database import Database
from app.db.models import IngestJobRecord


class IngestJobRepository:
    """入库任务仓库（SQLite）。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: IngestJobRecord) -> IngestJobRecord:
        """创建入库任务记录。"""

        self._db.execute(
            """
            INSERT INTO ingest_job (
                job_id, kb_id, doc_id, status, progress_json,
                error_message, error_code, started_at, finished_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.job_id,
                record.kb_id,
                record.doc_id,
                record.status,
                self._dumps(record.progress),
                record.error_message,
                record.error_code,
                record.started_at,
                record.finished_at,
                record.created_at,
                record.updated_at,
            ),
        )
        return record

    def get(self, job_id: str) -> IngestJobRecord | None:
        """获取入库任务记录。"""

        row = self._db.fetch_one(
            """
            SELECT job_id, kb_id, doc_id, status, progress_json,
                   error_message, error_code, started_at, finished_at, created_at, updated_at
            FROM ingest_job
            WHERE job_id = ?;
            """,
            (job_id,),
        )
        if row is None:
            return None
        return IngestJobRecord(
            job_id=row["job_id"],
            kb_id=row["kb_id"],
            doc_id=row["doc_id"],
            status=row["status"],
            progress=self._loads(row["progress_json"]),
            error_message=row["error_message"],
            error_code=row["error_code"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update(self, record: IngestJobRecord) -> IngestJobRecord:
        """更新入库任务记录。"""

        self._db.execute(
            """
            UPDATE ingest_job
            SET status = ?, progress_json = ?, error_message = ?, error_code = ?,
                started_at = ?, finished_at = ?, updated_at = ?
            WHERE job_id = ?;
            """,
            (
                record.status,
                self._dumps(record.progress),
                record.error_message,
                record.error_code,
                record.started_at,
                record.finished_at,
                record.updated_at,
                record.job_id,
            ),
        )
        return record

    def delete_by_doc_id(self, doc_id: str) -> None:
        """按文档删除入库任务。"""

        self._db.execute("DELETE FROM ingest_job WHERE doc_id = ?;", (doc_id,))

    def delete_by_kb_id(self, kb_id: str) -> None:
        """按知识库删除入库任务。"""

        self._db.execute("DELETE FROM ingest_job WHERE kb_id = ?;", (kb_id,))

    @staticmethod
    def _dumps(payload: object | None) -> str | None:
        """序列化 JSON。"""

        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _loads(payload: str | None) -> dict[str, object] | None:
        """反序列化 JSON。"""

        if not payload:
            return None
        return json.loads(payload)
