from __future__ import annotations

from uuid import UUID

import pytest

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.rag.vector_store import (
    InMemoryVectorStore,
    QdrantVectorStore,
    VectorEntry,
    _to_qdrant_point_id,
    _is_published_after_matched,
)


def test_payload_validation_missing_fields() -> None:
    store = InMemoryVectorStore()
    entry = VectorEntry(vector=[0.1], payload={"kb_id": "kb_1"})
    with pytest.raises(AppError) as exc_info:
        store.upsert(kb_id="kb_1", entries=[entry])
    assert exc_info.value.code == ErrorCode.RAG_PAYLOAD_INVALID


def test_payload_validation_reports_field_type() -> None:
    store = InMemoryVectorStore()
    entry = VectorEntry(
        vector=[0.1],
        payload={
            "contract_version": "0.1",
            "kb_id": "kb_1",
            "doc_id": "doc_1",
            "doc_name": "demo.pdf",
            "doc_version": None,
            "published_at": "2025-01-01",
            "published_at_ts": 1735689600,
            "page_start": "1",
            "page_end": 1,
            "section_path": None,
            "chunk_id": "chunk_1",
            "chunk_index": 0,
            "text": "test",
        },
    )

    with pytest.raises(AppError) as exc_info:
        store.upsert(kb_id="kb_1", entries=[entry])

    assert exc_info.value.code == ErrorCode.RAG_PAYLOAD_INVALID
    assert exc_info.value.detail is not None
    assert exc_info.value.detail["field"] == "page_start"
    assert exc_info.value.detail["actual_type"] == "str"


def test_qdrant_upsert_passes_through_app_error() -> None:
    store = object.__new__(QdrantVectorStore)
    inner = AppError(
        code=ErrorCode.RAG_PAYLOAD_INVALID,
        message="向量 payload 字段类型不合法",
        detail={"field": "page_start"},
        status_code=500,
    )

    def _raise_app_error(operation: object) -> object:
        del operation
        raise inner

    store._run_with_retry = _raise_app_error  # type: ignore[attr-defined]

    with pytest.raises(AppError) as exc_info:
        store.upsert(kb_id="kb_1", entries=[])

    assert exc_info.value is inner


def test_published_after_match_prefers_timestamp_field() -> None:
    payload = {
        "published_at": "2025-01-01",
        "published_at_ts": 1735776000,  # 2025-01-02T00:00:00Z
    }
    assert _is_published_after_matched(payload, "2025-01-02")
    assert not _is_published_after_matched(payload, "2025-01-03")


def test_qdrant_search_fallback_for_legacy_payload_without_timestamp() -> None:
    class _FakeResult:
        def __init__(self, score: float, payload: dict[str, object]) -> None:
            self.score = score
            self.payload = payload

    class _FakeFieldCondition:
        def __init__(
            self,
            key: str,
            match: object | None = None,
            range: object | None = None,
        ) -> None:
            self.key = key
            self.match = match
            self.range = range

    class _FakeMatchAny:
        def __init__(self, any: list[str]) -> None:
            self.any = any

    class _FakeRange:
        def __init__(self, gte: int | None = None) -> None:
            self.gte = gte

    class _FakeFilter:
        def __init__(self, must: list[object]) -> None:
            self.must = must

    class _FakeRest:
        FieldCondition = _FakeFieldCondition
        MatchAny = _FakeMatchAny
        Range = _FakeRange
        Filter = _FakeFilter

    class _FakeClient:
        def __init__(self) -> None:
            self.query_filters: list[object | None] = []

        def search(
            self,
            collection_name: str,
            query_vector: list[float],
            limit: int,
            with_payload: bool,
            query_filter: object | None,
        ) -> list[_FakeResult]:
            del collection_name, query_vector, limit, with_payload
            self.query_filters.append(query_filter)
            if query_filter is not None and any(
                getattr(condition, "key", "") == "published_at_ts"
                for condition in getattr(query_filter, "must", [])
            ):
                return []
            return [
                _FakeResult(
                    score=0.91,
                    payload={
                        "chunk_id": "chunk_1",
                        "doc_id": "doc_1",
                        "published_at": "2025-01-02",
                    },
                )
            ]

    store = object.__new__(QdrantVectorStore)
    store._rest = _FakeRest
    store._client = _FakeClient()
    store._run_with_retry = lambda operation: operation()
    store._collection_exists = lambda kb_id: True
    store._collection_name = lambda kb_id: f"csage_{kb_id}"

    hits = store.search(
        kb_id="kb_1",
        query_vector=[0.1, 0.2, 0.3],
        topk=1,
        filters={"published_after": "2025-01-01"},
    )

    assert len(hits) == 1
    assert hits[0].payload["chunk_id"] == "chunk_1"
    assert len(store._client.query_filters) == 2
    first_filter = store._client.query_filters[0]
    assert first_filter is not None
    assert any(
        getattr(condition, "key", "") == "published_at_ts"
        for condition in getattr(first_filter, "must", [])
    )
    assert store._client.query_filters[1] is None


def test_qdrant_point_id_is_stable_uuid() -> None:
    first = _to_qdrant_point_id("chunk_abc123")
    second = _to_qdrant_point_id("chunk_abc123")
    third = _to_qdrant_point_id("chunk_other")

    assert first == second
    assert first != third
    assert str(UUID(first)) == first


def test_qdrant_client_disables_system_proxy() -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_client_cls(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    store = object.__new__(QdrantVectorStore)
    store._client_cls = fake_client_cls
    store._qdrant_url = "http://127.0.0.1:6333"
    store._qdrant_api_key = None
    store._qdrant_timeout_s = 30

    client = QdrantVectorStore._create_client(store)

    assert client is sentinel
    assert captured["url"] == "http://127.0.0.1:6333"
    assert captured["trust_env"] is False
