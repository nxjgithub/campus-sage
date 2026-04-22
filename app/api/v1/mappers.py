"""API 响应映射函数。"""

from __future__ import annotations

from app.api.v1.schemas.conversations import ConversationListItem, MessageItem
from app.api.v1.schemas.documents import DocumentResponse
from app.api.v1.schemas.ingest import IngestJobResponse
from app.api.v1.schemas.kb import KnowledgeBaseListItem, KnowledgeBaseResponse
from app.api.v1.schemas.rag import AskResponse, Citation, NextStep
from app.db.models import (
    ConversationRecord,
    DocumentRecord,
    IngestJobRecord,
    KnowledgeBaseRecord,
    MessageRecord,
)
from app.rag.dto import AskResult, CitationDTO, NextStepDTO


def kb_to_response(record: KnowledgeBaseRecord, request_id: str | None) -> KnowledgeBaseResponse:
    """转换知识库响应。"""

    return KnowledgeBaseResponse(
        kb_id=record.kb_id,
        name=record.name,
        description=record.description,
        visibility=record.visibility,
        config=record.config,
        created_at=record.created_at,
        updated_at=record.updated_at,
        request_id=request_id,
    )


def kb_to_list_item(record: KnowledgeBaseRecord) -> KnowledgeBaseListItem:
    """转换知识库列表项。"""

    return KnowledgeBaseListItem(
        kb_id=record.kb_id,
        name=record.name,
        visibility=record.visibility,
        updated_at=record.updated_at,
    )


def doc_to_response(record: DocumentRecord) -> DocumentResponse:
    """转换文档响应。"""

    return DocumentResponse(
        doc_id=record.doc_id,
        kb_id=record.kb_id,
        doc_name=record.doc_name,
        doc_version=record.doc_version,
        published_at=record.published_at,
        source_uri=record.source_uri,
        status=record.status,
        error_message=record.error_message,
        chunk_count=record.chunk_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def job_to_response(record: IngestJobRecord) -> IngestJobResponse:
    """转换入库任务响应。"""

    progress = record.progress
    if progress is not None and "stage" not in progress:
        progress = dict(progress)
        progress["stage"] = _default_stage(record.status)
    return IngestJobResponse(
        job_id=record.job_id,
        kb_id=record.kb_id,
        doc_id=record.doc_id,
        status=record.status,
        progress=progress,
        error_message=record.error_message,
        error_code=record.error_code,
        started_at=record.started_at,
        finished_at=record.finished_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def conversation_to_list_item(record: ConversationRecord) -> ConversationListItem:
    """转换会话列表项。"""

    return ConversationListItem(
        conversation_id=record.conversation_id,
        kb_id=record.kb_id,
        title=record.title,
        last_message_preview=record.last_message_preview,
        last_message_at=record.last_message_at,
        updated_at=record.updated_at,
    )


def message_to_item(record: MessageRecord) -> MessageItem:
    """转换消息条目。"""

    return MessageItem(
        message_id=record.message_id,
        role=record.role,
        content=record.content,
        citations=record.citations or None,
        refusal=record.refusal if record.role == "assistant" else None,
        refusal_reason=record.refusal_reason if record.role == "assistant" else None,
        suggestions=record.suggestions if record.role == "assistant" else None,
        next_steps=record.next_steps if record.role == "assistant" else None,
        timing=record.timing if record.role == "assistant" else None,
        created_at=record.created_at,
        request_id=record.request_id,
    )


def rag_result_to_response(result: AskResult) -> AskResponse:
    """转换问答响应。"""

    return AskResponse(
        answer=result.answer,
        refusal=result.refusal,
        refusal_reason=result.refusal_reason,
        suggestions=list(result.suggestions),
        next_steps=[_next_step_from_dto(item) for item in result.next_steps],
        citations=[_citation_from_dto(item) for item in result.citations],
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        user_message_id=result.user_message_id,
        assistant_created_at=result.assistant_created_at,
        timing=result.timing,
        request_id=result.request_id,
    )


def _citation_from_dto(dto: CitationDTO) -> Citation:
    return Citation(
        citation_id=dto.citation_id,
        doc_id=dto.doc_id,
        doc_name=dto.doc_name,
        doc_version=dto.doc_version,
        published_at=dto.published_at,
        source_uri=dto.source_uri,
        page_start=dto.page_start,
        page_end=dto.page_end,
        section_path=dto.section_path,
        chunk_id=dto.chunk_id,
        snippet=dto.snippet,
        score=dto.score,
    )


def _next_step_from_dto(dto: NextStepDTO) -> NextStep:
    return NextStep(
        action=dto.action,
        label=dto.label,
        detail=dto.detail,
        value=dto.value,
    )


def _default_stage(status: str) -> str:
    if status == "succeeded":
        return "done"
    if status == "failed":
        return "failed"
    if status == "canceled":
        return "canceled"
    return "running"
