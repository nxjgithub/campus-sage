"""API 依赖注入工厂。"""

from __future__ import annotations

from fastapi import Depends

from app.core.settings import Settings, get_settings
from app.db.database import get_database
from app.db.repos import RepositoryProvider
from app.ingest.service import DocumentService, KnowledgeBaseService
from app.rag.conversation_service import ConversationService
from app.rag.feedback_service import FeedbackService
from app.rag.service import RagService


def get_repo_provider(settings: Settings = Depends(get_settings)) -> RepositoryProvider:
    """获取仓库提供器。"""

    database = get_database(settings)
    return RepositoryProvider(database)


def get_kb_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> KnowledgeBaseService:
    """获取知识库服务。"""

    kb_repo = provider.knowledge_base()
    doc_repo = provider.document()
    job_repo = provider.ingest_job()
    return KnowledgeBaseService(kb_repo, doc_repo, job_repo, settings)


def get_document_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> DocumentService:
    """获取文档服务。"""

    doc_repo = provider.document()
    job_repo = provider.ingest_job()
    return DocumentService(doc_repo, job_repo, settings)


def get_rag_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> RagService:
    """获取问答服务。"""

    kb_repo = provider.knowledge_base()
    return RagService(kb_repo, settings)


def get_conversation_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> ConversationService:
    """获取会话服务。"""

    repository = provider.conversation()
    return ConversationService(repository)


def get_feedback_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> FeedbackService:
    """获取反馈服务。"""

    repository = provider.conversation()
    return FeedbackService(repository)
