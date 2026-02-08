"""仓库接口定义。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.db.models import (
    ConversationRecord,
    DocumentRecord,
    FeedbackRecord,
    IngestJobRecord,
    KnowledgeBaseRecord,
    MessageRecord,
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
        self, kb_id: str | None, limit: int, offset: int
    ) -> list[ConversationRecord]: ...

    def create_message(self, record: MessageRecord) -> MessageRecord: ...

    def list_messages(self, conversation_id: str) -> list[MessageRecord]: ...

    def get_message(self, message_id: str) -> MessageRecord | None: ...

    def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord: ...
