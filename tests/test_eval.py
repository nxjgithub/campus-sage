from __future__ import annotations

from app.core.settings import Settings
from app.eval.dto import EvalItem, EvalSet
from app.eval.runner import run_eval
from app.rag.embedding import SimpleEmbedder
from app.rag.vector_store import InMemoryVectorStore, VectorEntry


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
