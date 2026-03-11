"""文档记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DocumentRecord:
    """文档记录。"""

    doc_id: str
    kb_id: str
    doc_name: str
    doc_version: str | None
    published_at: str | None
    source_uri: str | None
    status: str
    error_message: str | None
    chunk_count: int
    file_path: str | None
    created_at: str
    updated_at: str
    deleted: bool
