"""内存存储模型（仅用于低依赖演示）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.db.models.document import DocumentRecord
from app.db.models.ingest_job import IngestJobRecord
from app.db.models.knowledge_base import KnowledgeBaseRecord


@dataclass(slots=True)
class InMemoryStore:
    """内存存储（MVP 用于降低依赖复杂度）。"""

    kb_items: dict[str, KnowledgeBaseRecord] = field(default_factory=dict)
    docs: dict[str, DocumentRecord] = field(default_factory=dict)
    jobs: dict[str, IngestJobRecord] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def lock(self) -> Lock:
        """返回锁，便于服务层显式控制并发。"""

        return self._lock


store = InMemoryStore()
