"""仓库提供器（统一创建仓库实例）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.repos.conversation import ConversationRepository
from app.db.repos.document import DocumentRepository
from app.db.repos.ingest_job import IngestJobRepository
from app.db.repos.knowledge_base import KnowledgeBaseRepository


class RepositoryProvider:
    """仓库提供器。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def knowledge_base(self) -> KnowledgeBaseRepository:
        """获取知识库仓库。"""

        return KnowledgeBaseRepository(self._db)

    def document(self) -> DocumentRepository:
        """获取文档仓库。"""

        return DocumentRepository(self._db)

    def ingest_job(self) -> IngestJobRepository:
        """获取入库任务仓库。"""

        return IngestJobRepository(self._db)

    def conversation(self) -> ConversationRepository:
        """获取会话仓库。"""

        return ConversationRepository(self._db)
