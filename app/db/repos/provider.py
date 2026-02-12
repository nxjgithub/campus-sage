"""仓库提供器（统一创建仓库实例）。"""

from __future__ import annotations

from app.db.database import Database
from app.db.repos.conversation import ConversationRepository
from app.db.repos.document import DocumentRepository
from app.db.repos.eval_item import EvalItemRepository
from app.db.repos.eval_result import EvalResultRepository
from app.db.repos.eval_run import EvalRunRepository
from app.db.repos.eval_set import EvalSetRepository
from app.db.repos.ingest_job import IngestJobRepository
from app.db.repos.kb_access import KbAccessRepository
from app.db.repos.knowledge_base import KnowledgeBaseRepository
from app.db.repos.refresh_token import RefreshTokenRepository
from app.db.repos.role import RoleRepository
from app.db.repos.user import UserRepository


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

    def user(self) -> UserRepository:
        """获取用户仓库。"""

        return UserRepository(self._db)

    def role(self) -> RoleRepository:
        """获取角色仓库。"""

        return RoleRepository(self._db)

    def kb_access(self) -> KbAccessRepository:
        """获取知识库权限仓库。"""

        return KbAccessRepository(self._db)

    def refresh_token(self) -> RefreshTokenRepository:
        """获取刷新令牌仓库。"""

        return RefreshTokenRepository(self._db)

    def eval_set(self) -> EvalSetRepository:
        """获取评测集仓库。"""

        return EvalSetRepository(self._db)

    def eval_item(self) -> EvalItemRepository:
        """获取评测样本仓库。"""

        return EvalItemRepository(self._db)

    def eval_run(self) -> EvalRunRepository:
        """获取评测运行仓库。"""

        return EvalRunRepository(self._db)

    def eval_result(self) -> EvalResultRepository:
        """获取评测结果仓库。"""

        return EvalResultRepository(self._db)
