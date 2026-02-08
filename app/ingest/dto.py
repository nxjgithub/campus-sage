"""入库领域 DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PreparedDocument:
    """已准备好的文档入库信息。"""

    kb_id: str
    doc_id: str
    job_id: str
    doc_name: str
    doc_version: str | None
    published_at: str | None
    storage_path: Path
    extension: str


@dataclass(slots=True)
class IngestResult:
    """入库流水线结果。"""

    pages_parsed: int
    chunk_count: int
    embed_count: int
    upsert_count: int
    parse_ms: int
    chunk_ms: int
    embed_ms: int
    upsert_ms: int
    total_ms: int
