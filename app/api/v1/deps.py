"""API 依赖注入工厂。"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthService, AuthorizationService, UserService
from app.auth.tokens import TokenService
from app.core.settings import Settings, get_settings
from app.db.database import get_database
from app.db.repos import RepositoryProvider
from app.eval.service import EvalService
from app.ingest.service import DocumentService, KnowledgeBaseService
from app.rag.conversation_service import ConversationService
from app.rag.chat_run_service import ChatRunService
from app.rag.feedback_service import FeedbackService
from app.rag.service import RagService

_security = HTTPBearer(auto_error=False)

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


def get_chat_run_service(
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> ChatRunService:
    """获取聊天运行服务。"""

    return ChatRunService(provider.chat_run())


def get_user_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> UserService:
    """获取用户服务。"""

    user_repo = provider.user()
    role_repo = provider.role()
    kb_access_repo = provider.kb_access()
    return UserService(user_repo, role_repo, kb_access_repo, settings)


def get_eval_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> EvalService:
    """获取评测服务。"""

    return EvalService(
        eval_set_repo=provider.eval_set(),
        eval_item_repo=provider.eval_item(),
        eval_run_repo=provider.eval_run(),
        eval_result_repo=provider.eval_result(),
        kb_repo=provider.knowledge_base(),
        settings=settings,
    )


def get_auth_service(
    settings: Settings = Depends(get_settings),
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> AuthService:
    """获取认证服务。"""

    user_repo = provider.user()
    role_repo = provider.role()
    refresh_repo = provider.refresh_token()
    return AuthService(user_repo, role_repo, refresh_repo, settings)


def get_authorization_service(
    provider: RepositoryProvider = Depends(get_repo_provider),
) -> AuthorizationService:
    """获取授权服务。"""

    kb_access_repo = provider.kb_access()
    return AuthorizationService(kb_access_repo)


def get_optional_user(
    settings: Settings = Depends(get_settings),
    auth_service: AuthService = Depends(get_auth_service),
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> CurrentUser | None:
    """获取当前用户（允许匿名）。"""

    if credentials is None:
        return None
    token_service = TokenService(settings)
    payload = token_service.decode_access_token(credentials.credentials)
    return auth_service.build_current_user(payload.user_id)


def get_current_user(
    settings: Settings = Depends(get_settings),
    auth_service: AuthService = Depends(get_auth_service),
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> CurrentUser:
    """获取当前用户。"""

    if credentials is None:
        from app.core.errors import AppError
        from app.core.error_codes import ErrorCode

        raise AppError(
            code=ErrorCode.AUTH_UNAUTHORIZED,
            message="未登录",
            detail=None,
            status_code=401,
        )
    token_service = TokenService(settings)
    payload = token_service.decode_access_token(credentials.credentials)
    return auth_service.build_current_user(payload.user_id)


def require_permission(permission: str):
    """权限依赖注入。"""

    def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
        authz: AuthorizationService = Depends(get_authorization_service),
    ) -> CurrentUser:
        authz.ensure_permission(current_user, permission)
        return current_user

    return _dependency


def require_admin(
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> CurrentUser:
    """管理员权限依赖（语义包装）。"""

    return current_user
