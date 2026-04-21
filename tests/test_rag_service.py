from __future__ import annotations

from types import SimpleNamespace

from app.core.settings import Settings
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
