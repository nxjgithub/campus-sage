from __future__ import annotations

from types import SimpleNamespace

from app.core.settings import Settings
from app.core.utils import utc_now_iso
from app.db.models import ConversationRecord, MessageRecord
from app.rag.context_builder import ContextBuilder
from app.rag.dialog_policy import DialogState, IntentDecision
from app.rag.embedding import SimpleEmbedder
from app.rag.reranker import SimpleReranker
from app.rag.service import RagService
from app.rag.vector_store import VectorHit


def test_compute_answer_expands_candidate_pool_before_rerank() -> None:
    settings = Settings(
        _env_file=None,
        vllm_enabled=False,
        rag_threshold=0.0,
        rag_min_keyword_coverage=0.0,
        rag_rerank_candidate_multiplier=2,
        rag_rerank_candidate_cap=3,
    )
    search_calls: list[int] = []

    class _StubVectorStore:
        def search(
            self,
            kb_id: str,
            query_vector: list[float],
            topk: int,
            filters: dict[str, object] | None = None,
        ) -> list[VectorHit]:
            del kb_id, query_vector, filters
            search_calls.append(topk)
            all_hits = [
                VectorHit(
                    score=0.99,
                    payload={
                        "doc_id": "doc_other_1",
                        "doc_name": "其他文档1.md",
                        "doc_version": None,
                        "published_at": "2025-01-01",
                        "source_uri": None,
                        "page_start": None,
                        "page_end": None,
                        "section_path": None,
                        "chunk_id": "chunk_other_1",
                        "chunk_index": 0,
                        "text": "这是无关说明。",
                    },
                ),
                VectorHit(
                    score=0.97,
                    payload={
                        "doc_id": "doc_other_2",
                        "doc_name": "其他文档2.md",
                        "doc_version": None,
                        "published_at": "2025-01-01",
                        "source_uri": None,
                        "page_start": None,
                        "page_end": None,
                        "section_path": None,
                        "chunk_id": "chunk_other_2",
                        "chunk_index": 0,
                        "text": "这里讨论图书馆开放时间。",
                    },
                ),
                VectorHit(
                    score=0.61,
                    payload={
                        "doc_id": "doc_target",
                        "doc_name": "本科生考试管理规定.md",
                        "doc_version": None,
                        "published_at": "2025-01-01",
                        "source_uri": None,
                        "page_start": None,
                        "page_end": None,
                        "section_path": None,
                        "chunk_id": "chunk_target",
                        "chunk_index": 0,
                        "text": "补考申请条件一般适用于课程考核未通过且符合学校规定的学生。",
                    },
                ),
            ]
            return all_hits[:topk]

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()

    result = service._compute_answer(
        kb=SimpleNamespace(
            kb_id="kb_test",
            config={
                "topk": 2,
                "threshold": 0.0,
                "rerank_enabled": True,
                "min_evidence_chunks": 1,
                "min_context_chars": 1,
                "min_keyword_coverage": 0.0,
            },
        ),
        question="补考申请条件一般适用于哪些学生情形？",
        topk=None,
        threshold=None,
        rerank_enabled=None,
        filters=None,
        debug=False,
        normalized_question="补考申请条件一般适用于哪些学生情形",
        dialog_state=DialogState(
            turn_count=0,
            last_user_question=None,
            pending_clarification=False,
            history_text="",
        ),
        intent_decision=IntentDecision(
            intent="qa",
            normalized_question="补考申请条件一般适用于哪些学生情形",
            retrieval_query="补考申请条件一般适用于哪些学生情形？",
        ),
    )

    assert search_calls == [3]
    assert result.refusal is False
    assert result.citations[0].doc_name == "本科生考试管理规定.md"


def test_ask_stream_uses_vllm_delta_stream_before_saving_message() -> None:
    settings = Settings(
        _env_file=None,
        vllm_enabled=True,
        rag_threshold=0.0,
        rag_min_keyword_coverage=0.0,
        rag_min_context_chars=1,
    )
    saved_messages: list[MessageRecord] = []

    class _StubKbRepo:
        def get(self, kb_id: str):
            return SimpleNamespace(
                kb_id=kb_id,
                deleted=False,
                config={
                    "topk": 1,
                    "threshold": 0.0,
                    "rerank_enabled": False,
                    "min_evidence_chunks": 1,
                    "min_context_chars": 1,
                    "min_keyword_coverage": 0.0,
                },
            )

    class _StubVectorStore:
        def search(
            self,
            kb_id: str,
            query_vector: list[float],
            topk: int,
            filters: dict[str, object] | None = None,
        ) -> list[VectorHit]:
            del kb_id, query_vector, topk, filters
            return [
                VectorHit(
                    score=0.99,
                    payload={
                        "doc_id": "doc_stream",
                        "doc_name": "流式测试.md",
                        "doc_version": None,
                        "published_at": "2025-01-01",
                        "source_uri": None,
                        "page_start": None,
                        "page_end": None,
                        "section_path": "测试章节",
                        "chunk_id": "chunk_stream",
                        "chunk_index": 0,
                        "text": "补考申请条件需要符合学校考试管理规定。",
                    },
                )
            ]

    class _StubConversationService:
        def ensure_conversation(
            self,
            kb_id: str,
            conversation_id: str | None,
            title: str | None,
            user_id: str | None,
        ) -> ConversationRecord:
            del title, user_id
            now = utc_now_iso()
            return ConversationRecord(
                conversation_id=conversation_id or "conv_stream",
                kb_id=kb_id,
                user_id=None,
                title=None,
                created_at=now,
                updated_at=now,
                deleted=False,
            )

        def list_messages(self, conversation_id: str) -> list[MessageRecord]:
            del conversation_id
            return []

        def get_memory(self, conversation_id: str):
            del conversation_id
            return None

        def refresh_memory(self, conversation_id: str) -> None:
            del conversation_id

        def save_message(
            self,
            conversation_id: str,
            role: str,
            content: str,
            refusal: bool,
            refusal_reason: str | None,
            timing: dict[str, int] | None,
            suggestions: list[str] | None,
            next_steps: list[dict[str, object]] | None,
            citations: list[dict[str, object]] | None,
            request_id: str | None = None,
            message_id: str | None = None,
            parent_message_id: str | None = None,
            edited_from_message_id: str | None = None,
        ) -> MessageRecord:
            del edited_from_message_id
            record = MessageRecord(
                message_id=message_id or f"msg_{len(saved_messages) + 1}",
                conversation_id=conversation_id,
                role=role,
                content=content,
                refusal=refusal,
                refusal_reason=refusal_reason,
                timing=timing,
                suggestions=suggestions or [],
                next_steps=next_steps or [],
                citations=citations or [],
                created_at=utc_now_iso(),
                request_id=request_id,
                parent_message_id=parent_message_id,
            )
            saved_messages.append(record)
            return record

    class _StubLlmClient:
        def stream_generate(self, question: str, context: str, cancel_checker=None):
            del question, context, cancel_checker
            yield "第一段"
            yield "第二段"

    service = object.__new__(RagService)
    service._kb_repo = _StubKbRepo()
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._llm_client = _StubLlmClient()
    service._reranker = SimpleReranker()
    service._conversation_service = _StubConversationService()
    service._logger = None
    service._log_ask = lambda **kwargs: None

    events = list(
        service.ask_stream(
            kb_id="kb_stream",
            question="补考申请条件是什么？",
            request_id="req_stream",
            conversation_id=None,
            user_id=None,
            topk=None,
            threshold=None,
            rerank_enabled=None,
            filters=None,
            debug=False,
            run_id="run_stream",
            cancel_checker=lambda: False,
        )
    )

    token_deltas = [item["data"]["delta"] for item in events if item["event"] == "token"]
    assistant_messages = [item for item in saved_messages if item.role == "assistant"]
    assert token_deltas == ["第一段", "第二段", "\n\n参考：[1]"]
    assert assistant_messages[0].content == "第一段第二段\n\n参考：[1]"
    assert events[-1]["event"] == "done"
