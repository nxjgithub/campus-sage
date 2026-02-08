"""知识库记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KnowledgeBaseRecord:
    """知识库记录。"""

    kb_id: str
    name: str
    description: str | None
    visibility: str
    config: dict[str, object]
    created_at: str
    updated_at: str
    deleted: bool
