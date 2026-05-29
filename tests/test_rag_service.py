from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.core.utils import utc_now_iso
from app.db.models import ConversationRecord, MessageRecord
from app.rag.context_builder import ContextBuilder
from app.rag.dto import CitationDTO
from app.rag.dialog_policy import DialogState, IntentDecision
from app.rag.embedding import SimpleEmbedder
from app.rag.reranker import SimpleReranker
from app.rag.service import RagService
from app.rag.vector_store import VectorHit


def test_compute_answer_expands_candidate_pool_before_rerank() -> None:
    settings = Settings(
        _env_file=None,
        vllm_enabled=True,
        rag_threshold=0.0,
        rag_min_keyword_coverage=0.0,
        rag_rerank_candidate_multiplier=2,
        rag_rerank_candidate_cap=3,
    )
    search_calls: list[int] = []
    generate_calls: list[tuple[str, str]] = []

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

    class _StubLlmClient:
        def generate(self, question: str, context: str) -> str:
            generate_calls.append((question, context))
            return "符合学校规定的学生可申请补考。"

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()
    service._llm_client = _StubLlmClient()

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
    assert generate_calls
    assert result.refusal is False
    assert result.answer == "符合学校规定的学生可申请补考。\n\n参考：[1][2]"
    assert result.citations[0].doc_name == "本科生考试管理规定.md"


def test_compute_answer_requires_llm_for_normal_answer() -> None:
    settings = Settings(
        _env_file=None,
        vllm_enabled=False,
        rag_threshold=0.0,
        rag_min_keyword_coverage=0.0,
        rag_min_context_chars=1,
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
                )
            ]

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()

    with pytest.raises(AppError) as exc_info:
        service._compute_answer(
            kb=SimpleNamespace(
                kb_id="kb_test",
                config={
                    "topk": 1,
                    "threshold": 0.0,
                    "rerank_enabled": False,
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

    assert exc_info.value.code == ErrorCode.RAG_MODEL_FAILED
    assert exc_info.value.detail == {"vllm_enabled": False}


def test_compute_answer_returns_identity_without_retrieval_or_llm() -> None:
    settings = Settings(_env_file=None, vllm_enabled=False)

    class _FailingVectorStore:
        def search(self, *args, **kwargs) -> list[VectorHit]:
            del args, kwargs
            raise AssertionError("身份认知回答不应触发向量检索")

    class _FailingLlmClient:
        def generate(self, question: str, context: str) -> str:
            del question, context
            raise AssertionError("身份认知回答不应触发生成模型")

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _FailingVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()
    service._llm_client = _FailingLlmClient()

    result = service._compute_answer(
        kb=SimpleNamespace(
            kb_id="kb_test",
            config={
                "topk": 5,
                "threshold": 0.25,
                "rerank_enabled": True,
            },
        ),
        question="你是谁？",
        topk=None,
        threshold=None,
        rerank_enabled=None,
        filters=None,
        debug=False,
        normalized_question="你是谁",
        dialog_state=DialogState(
            turn_count=0,
            last_user_question=None,
            pending_clarification=False,
            history_text="",
        ),
        intent_decision=IntentDecision(
            intent="identity",
            normalized_question="你是谁",
            retrieval_query="你是谁？",
            direct_answer="我是 CampusSage。",
        ),
    )

    assert result.refusal is False
    assert result.answer == "我是 CampusSage。"
    assert result.citations == []
    assert result.timing["retrieve_ms"] == 0
    assert result.timing["generate_ms"] == 0


def test_compute_answer_recommends_questions_without_vector_search() -> None:
    settings = Settings(_env_file=None, vllm_enabled=True)

    class _StubVectorStore:
        def search(self, *args, **kwargs) -> list[VectorHit]:
            del args, kwargs
            raise AssertionError("推荐问题不应触发向量相似度检索")

        def sample_payloads(self, kb_id: str, limit: int = 12) -> list[dict[str, object]]:
            del kb_id, limit
            return [
                {
                    "doc_id": "doc_notice",
                    "doc_name": "补考通知.md",
                    "section_path": "考试管理/补考",
                    "text": "补考申请条件、确认时间和考试安排以教务系统通知为准。",
                }
            ]

    class _StubLlmClient:
        def generate_question_suggestions(
            self,
            kb_name: str,
            source_context: str,
            user_question: str | None = None,
            count: int = 4,
        ) -> list[str]:
            del kb_name, source_context, user_question, count
            return ["补考申请条件是什么？", "补考确认时间在哪里查看？"]

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()
    service._llm_client = _StubLlmClient()

    result = service._compute_answer(
        kb=SimpleNamespace(
            kb_id="kb_test",
            name="测试知识库",
            config={"topk": 5, "threshold": 0.25, "rerank_enabled": True},
        ),
        question="我可以问哪些问题？",
        topk=None,
        threshold=None,
        rerank_enabled=None,
        filters=None,
        debug=False,
        normalized_question="我可以问哪些问题",
        dialog_state=DialogState(
            turn_count=0,
            last_user_question=None,
            pending_clarification=False,
            history_text="",
        ),
        intent_decision=IntentDecision(
            intent="question_recommendation",
            normalized_question="我可以问哪些问题",
            retrieval_query="我可以问哪些问题？",
            recommend_questions=True,
        ),
    )

    assert result.refusal is False
    assert result.citations == []
    assert "补考申请条件是什么？" in result.answer
    assert result.suggestions == ["补考申请条件是什么？", "补考确认时间在哪里查看？"]
    assert result.timing["retrieve_ms"] == 0


def test_refusal_guidance_adds_llm_question_suggestions() -> None:
    settings = Settings(
        _env_file=None,
        vllm_enabled=True,
        rag_threshold=0.5,
        rag_min_keyword_coverage=0.0,
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
            return []

        def sample_payloads(self, kb_id: str, limit: int = 12) -> list[dict[str, object]]:
            del kb_id, limit
            return [
                {
                    "doc_id": "doc_scholarship",
                    "doc_name": "奖学金评定办法.md",
                    "section_path": "学生资助/奖学金",
                    "text": "奖学金评定通常关注申请条件、评定流程、公示和异议处理。",
                }
            ]

    class _StubLlmClient:
        def generate_question_suggestions(
            self,
            kb_name: str,
            source_context: str,
            user_question: str | None = None,
            count: int = 4,
        ) -> list[str]:
            del kb_name, source_context, user_question, count
            return ["奖学金评定条件有哪些？"]

    service = object.__new__(RagService)
    service._settings = settings
    service._embedder = SimpleEmbedder(vector_dim=8)
    service._vector_store = _StubVectorStore()
    service._context_builder = ContextBuilder(settings.rag_max_context_tokens)
    service._reranker = SimpleReranker()
    service._llm_client = _StubLlmClient()

    result = service._compute_answer(
        kb=SimpleNamespace(
            kb_id="kb_test",
            name="学生事务知识库",
            config={
                "topk": 3,
                "threshold": 0.5,
                "rerank_enabled": False,
                "min_evidence_chunks": 1,
                "min_context_chars": 20,
                "min_keyword_coverage": 0.0,
            },
        ),
        question="完全无关的问题",
        topk=None,
        threshold=None,
        rerank_enabled=None,
        filters=None,
        debug=False,
        normalized_question="完全无关的问题",
        dialog_state=DialogState(
            turn_count=0,
            last_user_question=None,
            pending_clarification=False,
            history_text="",
        ),
        intent_decision=IntentDecision(
            intent="qa",
            normalized_question="完全无关的问题",
            retrieval_query="完全无关的问题",
        ),
    )

    assert result.refusal is True
    assert "可尝试提问：奖学金评定条件有哪些？" in result.suggestions
    assert any(step.value == "奖学金评定条件有哪些？" for step in result.next_steps)


def test_empty_llm_answer_does_not_fallback_to_retrieved_snippet() -> None:
    settings = Settings(_env_file=None, vllm_enabled=True)
    service = object.__new__(RagService)
    service._settings = settings

    with pytest.raises(AppError) as exc_info:
        service._ensure_citations_in_answer(
            "",
            [
                SimpleNamespace(
                    citation_id=1,
                    snippet="检索片段不能直接拼成正常回答。",
                )
            ],
        )

    assert exc_info.value.code == ErrorCode.RAG_MODEL_FAILED
    assert exc_info.value.detail == {"reason": "empty_answer"}


def test_build_citations_returns_attached_assets() -> None:
    settings = Settings(_env_file=None)
    service = object.__new__(RagService)
    service._settings = settings

    citations = service._build_citations(
        [
            VectorHit(
                score=0.88,
                payload={
                    "doc_id": "doc_image",
                    "doc_name": "图文通知.docx",
                    "doc_version": None,
                    "published_at": None,
                    "source_uri": None,
                    "page_start": None,
                    "page_end": None,
                    "section_path": "操作说明",
                    "chunk_id": "chunk_image",
                    "chunk_index": 0,
                    "text": "学生进入系统后按页面提示完成登记。",
                    "assets": [
                        {
                            "asset_id": "asset_1",
                            "asset_label": "图 1",
                            "asset_url": "/api/v1/assets/asset_1",
                            "media_type": "image/jpeg",
                            "file_name": "image1.jpeg",
                        }
                    ],
                },
            )
        ],
        debug=True,
    )

    assert citations[0].asset_id == "asset_1"
    assert citations[0].asset_label == "图 1"
    assert citations[0].assets[0].asset_url == "/api/v1/assets/asset_1"


def test_generated_result_only_returns_answer_cited_evidence() -> None:
    settings = Settings(_env_file=None)
    service = object.__new__(RagService)
    service._settings = settings

    prepared = SimpleNamespace(
        kb_id="kb_test",
        kb_name="测试知识库",
        normalized_question="如何获得证书？",
        citations=[
            _citation_dto(1, "doc_1", "证据一"),
            _citation_dto(2, "doc_2", "证据二"),
            _citation_dto(3, "doc_3", "证据三"),
        ],
        retrieve_ms=1,
        rerank_ms=2,
        context_ms=3,
        total_start=0.0,
        topk=3,
        threshold=0.25,
        rerank_enabled=True,
        hits_for_log=[],
        intent="qa",
        slots={},
    )

    result = service._build_generated_result(
        prepared=prepared,
        answer="根据证据1，完成学习和答题即可获得证书。[1]",
        generate_ms=4,
    )

    assert result.refusal is False
    assert [item.citation_id for item in result.citations] == [1]


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


def _citation_dto(citation_id: int, doc_id: str, snippet: str) -> CitationDTO:
    return CitationDTO(
        citation_id=citation_id,
        doc_id=doc_id,
        doc_name=f"{doc_id}.md",
        doc_version=None,
        published_at=None,
        source_uri=None,
        page_start=None,
        page_end=None,
        section_path="测试章节",
        chunk_id=f"chunk_{citation_id}",
        snippet=snippet,
        score=None,
    )
