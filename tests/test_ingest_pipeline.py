from __future__ import annotations

import pytest

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.ingest.chunker import Chunk
from app.ingest.parser import ParsedPage
from app.ingest.pipeline import IngestPipeline


def test_pipeline_raises_when_embedding_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    pipeline = IngestPipeline(settings)

    monkeypatch.setattr(
        pipeline._parser,
        "parse",
        lambda path: [ParsedPage(page_number=1, text="第一段。第二段。")],
    )
    chunks = [
        Chunk(chunk_index=0, text="第一段", page_start=1, page_end=1, section_path=None),
        Chunk(chunk_index=1, text="第二段", page_start=1, page_end=1, section_path=None),
    ]
    monkeypatch.setattr(pipeline._chunker, "build", lambda pages: chunks)
    monkeypatch.setattr(
        pipeline._embedder,
        "embed_texts",
        lambda texts: [[0.1, 0.2, 0.3]],
    )
    upsert_called = {"value": False}
    monkeypatch.setattr(
        pipeline._vector_store,
        "upsert",
        lambda kb_id, entries: upsert_called.__setitem__("value", True),
    )

    with pytest.raises(AppError) as exc_info:
        pipeline.run(
            kb_id="kb_1",
            doc_id="doc_1",
            doc_name="demo.pdf",
            doc_version="v1",
            published_at="2025-01-01",
            source_uri=None,
            file_path="ignored-by-monkeypatch",
        )

    assert exc_info.value.code == ErrorCode.INGEST_EMBED_FAILED
    assert exc_info.value.detail == {"chunk_count": 2, "vector_count": 1}
    assert not upsert_called["value"]


def test_pipeline_wraps_upsert_app_error_with_source_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    pipeline = IngestPipeline(settings)

    monkeypatch.setattr(
        pipeline._parser,
        "parse",
        lambda path: [ParsedPage(page_number=1, text="第一段。")],
    )
    monkeypatch.setattr(
        pipeline._chunker,
        "build",
        lambda pages: [
            Chunk(
                chunk_index=0,
                text="第一段",
                page_start=1,
                page_end=1,
                section_path=None,
            )
        ],
    )
    monkeypatch.setattr(pipeline._embedder, "embed_texts", lambda texts: [[0.1, 0.2, 0.3]])

    def _raise_upsert_error(kb_id: str, entries: list[object]) -> None:
        del kb_id, entries
        raise AppError(
            code=ErrorCode.VECTOR_UPSERT_FAILED,
            message="向量库不可用，无法写入",
            detail={"error": "Unexpected Response: 400 (Bad Request)"},
            status_code=503,
        )

    monkeypatch.setattr(pipeline._vector_store, "upsert", _raise_upsert_error)

    with pytest.raises(AppError) as exc_info:
        pipeline.run(
            kb_id="kb_1",
            doc_id="doc_1",
            doc_name="demo.pdf",
            doc_version="v1",
            published_at="2025-01-01",
            source_uri=None,
            file_path="ignored-by-monkeypatch",
        )

    assert exc_info.value.code == ErrorCode.VECTOR_UPSERT_FAILED
    assert exc_info.value.detail is not None
    assert exc_info.value.detail["source_code"] == ErrorCode.VECTOR_UPSERT_FAILED.value
    assert exc_info.value.detail["source_message"] == "向量库不可用，无法写入"
    assert exc_info.value.detail["source_detail"] == {
        "error": "Unexpected Response: 400 (Bad Request)"
    }


def test_pipeline_normalizes_payload_types_before_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    pipeline = IngestPipeline(settings)

    monkeypatch.setattr(
        pipeline._parser,
        "parse",
        lambda path: [ParsedPage(page_number=1, text="第一段")],
    )
    monkeypatch.setattr(
        pipeline._chunker,
        "build",
        lambda pages: [
            Chunk(
                chunk_index="2",  # type: ignore[arg-type]
                text=123,  # type: ignore[arg-type]
                page_start="3",  # type: ignore[arg-type]
                page_end=4.9,  # type: ignore[arg-type]
                section_path=5,  # type: ignore[arg-type]
            )
        ],
    )
    monkeypatch.setattr(pipeline._embedder, "embed_texts", lambda texts: [[0.1, 0.2, 0.3]])

    captured_entries: list[object] = []

    def _capture_upsert(kb_id: str, entries: list[object]) -> None:
        del kb_id
        captured_entries.extend(entries)

    monkeypatch.setattr(pipeline._vector_store, "upsert", _capture_upsert)

    result = pipeline.run(
        kb_id=100,  # type: ignore[arg-type]
        doc_id=200,  # type: ignore[arg-type]
        doc_name=300,  # type: ignore[arg-type]
        doc_version=400,  # type: ignore[arg-type]
        published_at=500,  # type: ignore[arg-type]
        source_uri=600,  # type: ignore[arg-type]
        file_path="ignored-by-monkeypatch",
    )

    assert result.upsert_count == 1
    assert len(captured_entries) == 1
    payload = captured_entries[0].payload  # type: ignore[attr-defined]
    assert payload["kb_id"] == "100"
    assert payload["doc_id"] == "200"
    assert payload["doc_name"] == "300"
    assert payload["doc_version"] == "400"
    assert payload["published_at"] == "500"
    assert payload["source_uri"] == "600"
    assert payload["page_start"] == 3
    assert payload["page_end"] == 4
    assert payload["section_path"] == "5"
    assert payload["chunk_index"] == 2
    assert payload["text"] == "123"


def test_pipeline_filters_blank_chunks_before_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    pipeline = IngestPipeline(settings)

    monkeypatch.setattr(
        pipeline._parser,
        "parse",
        lambda path: [ParsedPage(page_number=1, text="ignored")],
    )
    monkeypatch.setattr(
        pipeline._chunker,
        "build",
        lambda pages: [
            Chunk(chunk_index=0, text="   \n  ", page_start=1, page_end=1, section_path=None),
            Chunk(chunk_index=1, text="  有效文本  ", page_start=1, page_end=1, section_path=None),
        ],
    )
    embedded_texts: list[str] = []

    def _embed_texts(texts: list[str]) -> list[list[float]]:
        embedded_texts.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(pipeline._embedder, "embed_texts", _embed_texts)

    captured_entries: list[object] = []

    def _capture_upsert(kb_id: str, entries: list[object]) -> None:
        del kb_id
        captured_entries.extend(entries)

    monkeypatch.setattr(pipeline._vector_store, "upsert", _capture_upsert)

    result = pipeline.run(
        kb_id="kb_1",
        doc_id="doc_1",
        doc_name="demo.pdf",
        doc_version=None,
        published_at=None,
        source_uri=None,
        file_path="ignored-by-monkeypatch",
    )

    assert result.chunk_count == 1
    assert embedded_texts == ["有效文本"]
    assert len(captured_entries) == 1
    payload = captured_entries[0].payload  # type: ignore[attr-defined]
    assert payload["text"] == "有效文本"
