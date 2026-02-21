"""仓库接口定义。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.db.models import (
    ChatRunRecord,
    ConversationRecord,
    DocumentRecord,
    EvalItemRecord,
    EvalResultRecord,
    EvalRunRecord,
    EvalSetRecord,
    FeedbackRecord,
    IngestJobRecord,
    KbAccessRecord,
    KnowledgeBaseRecord,
    MessageRecord,
    RefreshTokenRecord,
    RoleRecord,
    UserRecord,
)


class KnowledgeBaseRepositoryProtocol(Protocol):
    """知识库仓库接口。"""

    def create(self, record: KnowledgeBaseRecord) -> KnowledgeBaseRecord: ...

    def get(self, kb_id: str) -> KnowledgeBaseRecord | None: ...

    def list_all(self) -> Iterable[KnowledgeBaseRecord]: ...

    def update(self, record: KnowledgeBaseRecord) -> KnowledgeBaseRecord: ...


class DocumentRepositoryProtocol(Protocol):
    """文档仓库接口。"""

    def create(self, record: DocumentRecord) -> DocumentRecord: ...

    def get(self, doc_id: str) -> DocumentRecord | None: ...

    def list_by_kb(self, kb_id: str) -> Iterable[DocumentRecord]: ...

    def update(self, record: DocumentRecord) -> DocumentRecord: ...

    def mark_deleted_by_kb(self, kb_id: str, updated_at: str) -> None: ...


class IngestJobRepositoryProtocol(Protocol):
    """入库任务仓库接口。"""

    def create(self, record: IngestJobRecord) -> IngestJobRecord: ...

    def get(self, job_id: str) -> IngestJobRecord | None: ...

    def update(self, record: IngestJobRecord) -> IngestJobRecord: ...

    def delete_by_doc_id(self, doc_id: str) -> None: ...

    def delete_by_kb_id(self, kb_id: str) -> None: ...


class ConversationRepositoryProtocol(Protocol):
    """会话仓库接口。"""

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None: ...

    def create_conversation(self, record: ConversationRecord) -> ConversationRecord: ...

    def update_conversation(self, record: ConversationRecord) -> ConversationRecord: ...

    def list_conversations(
        self,
        kb_id: str | None,
        user_id: str | None,
        keyword: str | None,
        cursor: str | None,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]: ...

    def count_conversations(
        self, kb_id: str | None, user_id: str | None, keyword: str | None
    ) -> int: ...

    def create_message(self, record: MessageRecord) -> MessageRecord: ...

    def list_messages(self, conversation_id: str) -> list[MessageRecord]: ...

    def list_messages_page(
        self, conversation_id: str, before_message_id: str | None, limit: int
    ) -> tuple[list[MessageRecord], bool, str | None]: ...

    def get_message(self, message_id: str) -> MessageRecord | None: ...

    def get_previous_user_message(
        self, conversation_id: str, before_message_id: str
    ) -> MessageRecord | None: ...

    def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord: ...


class ChatRunRepositoryProtocol(Protocol):
    """聊天运行仓库接口。"""

    def create(self, record: ChatRunRecord) -> ChatRunRecord: ...

    def get(self, run_id: str) -> ChatRunRecord | None: ...

    def update(self, record: ChatRunRecord) -> ChatRunRecord: ...


class UserRepositoryProtocol(Protocol):
    """用户仓库接口。"""

    def create(self, record: UserRecord) -> UserRecord: ...

    def get(self, user_id: str) -> UserRecord | None: ...

    def get_by_email(self, email: str) -> UserRecord | None: ...

    def list_all(self) -> list[UserRecord]: ...

    def list_filtered(
        self,
        status: str | None,
        keyword: str | None,
        limit: int,
        offset: int,
    ) -> list[UserRecord]: ...

    def count_filtered(self, status: str | None, keyword: str | None) -> int: ...

    def update(self, record: UserRecord) -> UserRecord: ...

    def set_roles(self, user_id: str, role_names: list[str]) -> None: ...

    def list_roles(self, user_id: str) -> list[RoleRecord]: ...


class RoleRepositoryProtocol(Protocol):
    """角色仓库接口。"""

    def create(self, record: RoleRecord) -> RoleRecord: ...

    def get_by_name(self, name: str) -> RoleRecord | None: ...

    def list_all(self) -> list[RoleRecord]: ...


class KbAccessRepositoryProtocol(Protocol):
    """知识库权限仓库接口。"""

    def get(self, user_id: str, kb_id: str) -> KbAccessRecord | None: ...

    def upsert(self, record: KbAccessRecord) -> KbAccessRecord: ...

    def delete(self, user_id: str, kb_id: str) -> bool: ...

    def list_by_user(self, user_id: str) -> list[KbAccessRecord]: ...

    def replace_by_user(self, user_id: str, records: list[KbAccessRecord]) -> None: ...


class RefreshTokenRepositoryProtocol(Protocol):
    """刷新令牌仓库接口。"""

    def create(self, record: RefreshTokenRecord) -> RefreshTokenRecord: ...

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    def revoke(self, token_id: str, revoked_at: str) -> None: ...


class EvalSetRepositoryProtocol(Protocol):
    """评测集仓库接口。"""

    def create(self, record: EvalSetRecord) -> EvalSetRecord: ...

    def get(self, eval_set_id: str) -> EvalSetRecord | None: ...


class EvalItemRepositoryProtocol(Protocol):
    """评测样本仓库接口。"""

    def create_many(self, records: list[EvalItemRecord]) -> None: ...

    def list_by_set(self, eval_set_id: str) -> list[EvalItemRecord]: ...


class EvalRunRepositoryProtocol(Protocol):
    """评测运行仓库接口。"""

    def create(self, record: EvalRunRecord) -> EvalRunRecord: ...

    def get(self, run_id: str) -> EvalRunRecord | None: ...

    def update_metrics(self, run_id: str, metrics_json: str | None) -> None: ...


class EvalResultRepositoryProtocol(Protocol):
    """评测结果仓库接口。"""

    def create_many(self, records: list[EvalResultRecord]) -> None: ...

    def list_by_run(self, run_id: str) -> list[EvalResultRecord]: ...
