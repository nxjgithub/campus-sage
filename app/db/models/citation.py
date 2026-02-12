from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CitationRecord:
    """引用记录。"""

    citation_row_id: str
    message_id: str
    citation_id: int
    doc_id: str
    doc_name: str
    doc_version: str | None
    published_at: str | None
    page_start: int | None
    page_end: int | None
    section_path: str | None
    chunk_id: str
    snippet: str
    score: float | None
    created_at: str
