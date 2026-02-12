from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.core.settings import Settings
from app.rag.vector_store import QdrantVectorStore, VectorEntry
from tests.conftest import is_qdrant_available


def test_qdrant_upsert_search_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URL", os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    monkeypatch.setenv("VECTOR_DIM", "4")

    settings = Settings()
    if not is_qdrant_available():
        pytest.skip("Qdrant 不可用，跳过集成测试")

    kb_id = f"kb_test_{uuid4().hex[:6]}"
    doc_id = f"doc_{uuid4().hex[:6]}"
    chunk_id = f"chunk_{uuid4().hex[:6]}"
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
        "chunk_id": chunk_id,
        "chunk_index": 0,
        "text": "测试文本",
    }
    entry = VectorEntry(vector=[0.1, 0.2, 0.3, 0.4], payload=payload)

    store = QdrantVectorStore(settings)
    try:
        store.upsert(kb_id=kb_id, entries=[entry])
        hits = store.search(kb_id=kb_id, query_vector=[0.1, 0.2, 0.3, 0.4], topk=1)
        assert hits

        store.delete_by_doc_id(kb_id=kb_id, doc_id=doc_id)
        hits_after_delete = store.search(
            kb_id=kb_id, query_vector=[0.1, 0.2, 0.3, 0.4], topk=1
        )
        assert not hits_after_delete
    finally:
        store.delete_by_kb_id(kb_id)
