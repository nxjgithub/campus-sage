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
            file_path="ignored-by-monkeypatch",
        )

    assert exc_info.value.code == ErrorCode.INGEST_EMBED_FAILED
    assert exc_info.value.detail == {"chunk_count": 2, "vector_count": 1}
    assert not upsert_called["value"]
