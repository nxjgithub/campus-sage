"""入库 Worker 公共工具。"""

from __future__ import annotations

from app.core.settings import Settings
from app.db.database import init_database, get_database
from app.db.repos import RepositoryProvider
from app.ingest.service import DocumentService


def build_document_service(settings: Settings) -> DocumentService:
    """构建文档服务实例。"""

    init_database(settings)
    database = get_database(settings)
    provider = RepositoryProvider(database)
    return DocumentService(provider.document(), provider.ingest_job(), settings)
