from __future__ import annotations

from app.core.settings import Settings
from app.eval.dto import EvalItem, EvalSet
from app.eval.runner import evaluate_items, run_eval
from app.rag.embedding import SimpleEmbedder
from app.rag.vector_store import InMemoryVectorStore, VectorEntry, VectorHit


def test_run_eval_returns_metrics() -> None:
    settings = Settings()
    embedder = SimpleEmbedder(vector_dim=8)
    store = InMemoryVectorStore()

    kb_id = "kb_eval"
    doc_id = "doc_eval"
    question = "补考 条件"
    vector = embedder.embed_query(question)
    payload = {
        "contract_version": "0.1",
        "kb_id": kb_id,
        "doc_id": doc_id,
        "doc_name": "demo.pdf",
        "doc_version": None,
        "published_at": "2025-01-01",
        "page_start": 1,
        "page_end": 1,
        "section_path": None,
        "chunk_id": "chunk_eval",
        "chunk_index": 0,
        "text": "补考 条件 说明",
    }
    store.upsert(kb_id=kb_id, entries=[VectorEntry(vector=vector, payload=payload)])

    eval_set = EvalSet(
        name="eval_test",
        items=[EvalItem(question=question, gold_doc_id=doc_id, gold_page_start=1, gold_page_end=1)],
    )
    result = run_eval(
        kb_id=kb_id,
        eval_set=eval_set,
        topk=5,
        settings=settings,
        embedder=embedder,
        vector_store=store,
    )

    assert result.samples == 1
    assert result.recall_at_k == 1.0
    assert result.mrr == 1.0


def test_run_eval_can_match_by_doc_name() -> None:
    settings = Settings()
    embedder = SimpleEmbedder(vector_dim=8)
    store = InMemoryVectorStore()

    kb_id = "kb_eval_name"
    question = "重修报名时间"
    vector = embedder.embed_query(question)
    payload = {
        "contract_version": "0.1",
        "kb_id": kb_id,
        "doc_id": "doc_generated_id",
        "doc_name": "选课与重修操作指南.pdf",
        "doc_version": None,
        "published_at": "2025-01-01",
        "page_start": 3,
        "page_end": 3,
        "section_path": None,
        "chunk_id": "chunk_eval_name",
        "chunk_index": 0,
        "text": "重修报名时间一般安排在开学初补退选阶段。",
    }
    store.upsert(kb_id=kb_id, entries=[VectorEntry(vector=vector, payload=payload)])

    eval_set = EvalSet(
        name="eval_by_doc_name",
        items=[
            EvalItem(
                question=question,
                gold_doc_id=None,
                gold_doc_name="选课与重修操作指南.pdf",
                gold_page_start=3,
                gold_page_end=3,
            )
        ],
    )
    result = run_eval(
        kb_id=kb_id,
        eval_set=eval_set,
        topk=5,
        settings=settings,
        embedder=embedder,
        vector_store=store,
    )

    assert result.samples == 1
    assert result.recall_at_k == 1.0
    assert result.mrr == 1.0


def test_evaluate_items_expands_candidate_pool_when_rerank_enabled() -> None:
    settings = Settings(
        _env_file=None,
        rag_rerank_candidate_multiplier=2,
        rag_rerank_candidate_cap=3,
    )
    embedder = SimpleEmbedder(vector_dim=8)
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
                    score=0.98,
                    payload={
                        "doc_id": "doc_other_1",
                        "doc_name": "其他文档1.md",
                        "chunk_id": "chunk_other_1",
                        "chunk_index": 0,
                        "text": "这是无关说明。",
                    },
                ),
                VectorHit(
                    score=0.96,
                    payload={
                        "doc_id": "doc_other_2",
                        "doc_name": "其他文档2.md",
                        "chunk_id": "chunk_other_2",
                        "chunk_index": 0,
                        "text": "这里讨论图书馆开放时间。",
                    },
                ),
                VectorHit(
                    score=0.60,
                    payload={
                        "doc_id": "doc_target",
                        "doc_name": "本科生考试管理规定.md",
                        "chunk_id": "chunk_target",
                        "chunk_index": 0,
                        "text": "补考申请条件一般适用于课程考核未通过且符合学校规定的学生。",
                    },
                ),
            ]
            return all_hits[:topk]

    eval_set = EvalSet(
        name="eval_rerank_candidates",
        items=[
            EvalItem(
                question="补考申请条件一般适用于哪些学生情形？",
                gold_doc_id=None,
                gold_doc_name="本科生考试管理规定.md",
                gold_page_start=None,
                gold_page_end=None,
            )
        ],
    )

    results = evaluate_items(
        kb_id="kb_eval_expand",
        eval_set=eval_set,
        topk=2,
        settings=settings,
        embedder=embedder,
        vector_store=_StubVectorStore(),
        rerank_enabled=True,
        threshold=None,
    )

    assert search_calls == [3]
    assert results[0].rank == 1
