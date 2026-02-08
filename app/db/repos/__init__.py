"""仓库层统一导出。"""

from app.db.repos.conversation import ConversationRepository
from app.db.repos.document import DocumentRepository
from app.db.repos.ingest_job import IngestJobRepository
from app.db.repos.interfaces import (
    ConversationRepositoryProtocol,
    DocumentRepositoryProtocol,
    IngestJobRepositoryProtocol,
    KnowledgeBaseRepositoryProtocol,
)
from app.db.repos.knowledge_base import KnowledgeBaseRepository
from app.db.repos.provider import RepositoryProvider

__all__ = [
    "ConversationRepository",
    "ConversationRepositoryProtocol",
    "DocumentRepository",
    "DocumentRepositoryProtocol",
    "IngestJobRepository",
    "IngestJobRepositoryProtocol",
    "KnowledgeBaseRepository",
    "KnowledgeBaseRepositoryProtocol",
    "RepositoryProvider",
]
