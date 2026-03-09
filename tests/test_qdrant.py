from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
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


def test_qdrant_search_uses_query_points_when_search_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VECTOR_BACKEND", "qdrant")
    monkeypatch.setenv("VECTOR_DIM", "4")

    settings = Settings()
    store = QdrantVectorStore(settings)
    store._collection_exists = lambda kb_id: True  # type: ignore[method-assign]
    store._search_points_rest_compat = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AppError(
            code=ErrorCode.VECTOR_SEARCH_FAILED,
            message="旧版 REST 接口不可用",
            detail={"status_code": 404},
            status_code=503,
        )
    )

    captured: dict[str, object] = {}

    class _FakeClient:
        def query_points(
            self,
            *,
            collection_name: str,
            query: list[float],
            limit: int,
            with_payload: bool,
            query_filter: object,
        ) -> SimpleNamespace:
            captured["collection_name"] = collection_name
            captured["query"] = query
            captured["limit"] = limit
            captured["with_payload"] = with_payload
            captured["query_filter"] = query_filter
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        score=0.91,
                        payload={"chunk_id": "chunk_demo", "doc_id": "doc_demo"},
                    )
                ]
            )

    store._client = _FakeClient()  # type: ignore[assignment]

    hits = store.search(kb_id="kb_demo", query_vector=[0.1, 0.2, 0.3, 0.4], topk=1)

    assert len(hits) == 1
    assert hits[0].score == 0.91
    assert hits[0].payload["chunk_id"] == "chunk_demo"
    assert captured["collection_name"] == f"{settings.qdrant_collection_prefix}kb_demo"
    assert captured["query"] == [0.1, 0.2, 0.3, 0.4]
    assert captured["limit"] == 1
    assert captured["with_payload"] is True
