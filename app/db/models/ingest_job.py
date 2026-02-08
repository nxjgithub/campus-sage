"""入库任务记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IngestJobRecord:
    """入库任务记录。"""

    job_id: str
    kb_id: str
    doc_id: str
    status: str
    progress: dict[str, object] | None
    error_message: str | None
    error_code: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str
