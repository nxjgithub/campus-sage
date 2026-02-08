"""文档仓库实现（SQLite）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.models import DocumentRecord


class DocumentRepository:
    """文档仓库（SQLite）。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, record: DocumentRecord) -> DocumentRecord:
        """创建文档记录。"""

        self._db.execute(
            """
            INSERT INTO document (
                doc_id, kb_id, doc_name, doc_version, published_at, status,
                error_message, chunk_count, file_path, created_at, updated_at, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.doc_id,
                record.kb_id,
                record.doc_name,
                record.doc_version,
                record.published_at,
                record.status,
                record.error_message,
                record.chunk_count,
                record.file_path,
                record.created_at,
                record.updated_at,
                int(record.deleted),
            ),
        )
        return record

    def get(self, doc_id: str) -> DocumentRecord | None:
        """获取文档记录。"""

        row = self._db.fetch_one(
            """
            SELECT doc_id, kb_id, doc_name, doc_version, published_at, status,
                   error_message, chunk_count, file_path, created_at, updated_at, deleted
            FROM document
            WHERE doc_id = ?;
            """,
            (doc_id,),
        )
        if row is None:
            return None
        return DocumentRecord(
            doc_id=row["doc_id"],
            kb_id=row["kb_id"],
            doc_name=row["doc_name"],
            doc_version=row["doc_version"],
            published_at=row["published_at"],
            status=row["status"],
            error_message=row["error_message"],
            chunk_count=int(row["chunk_count"]),
            file_path=row["file_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted=bool(row["deleted"]),
        )

    def list_by_kb(self, kb_id: str) -> list[DocumentRecord]:
        """按知识库列出文档。"""

        rows = self._db.fetch_all(
            """
            SELECT doc_id, kb_id, doc_name, doc_version, published_at, status,
                   error_message, chunk_count, file_path, created_at, updated_at, deleted
            FROM document
            WHERE kb_id = ? AND deleted = 0
            ORDER BY updated_at DESC;
            """,
            (kb_id,),
        )
        return [
            DocumentRecord(
                doc_id=row["doc_id"],
                kb_id=row["kb_id"],
                doc_name=row["doc_name"],
                doc_version=row["doc_version"],
                published_at=row["published_at"],
                status=row["status"],
                error_message=row["error_message"],
                chunk_count=int(row["chunk_count"]),
                file_path=row["file_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                deleted=bool(row["deleted"]),
            )
            for row in rows
        ]

    def update(self, record: DocumentRecord) -> DocumentRecord:
        """更新文档记录。"""

        self._db.execute(
            """
            UPDATE document
            SET doc_name = ?, doc_version = ?, published_at = ?, status = ?,
                error_message = ?, chunk_count = ?, file_path = ?, updated_at = ?, deleted = ?
            WHERE doc_id = ?;
            """,
            (
                record.doc_name,
                record.doc_version,
                record.published_at,
                record.status,
                record.error_message,
                record.chunk_count,
                record.file_path,
                record.updated_at,
                int(record.deleted),
                record.doc_id,
            ),
        )
        return record

    def mark_deleted_by_kb(self, kb_id: str, updated_at: str) -> None:
        """按知识库批量标记删除文档。"""

        self._db.execute(
            """
            UPDATE document
            SET deleted = 1, status = 'deleted', updated_at = ?
            WHERE kb_id = ?;
            """,
            (updated_at, kb_id),
        )
