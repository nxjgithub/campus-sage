from __future__ import annotations

import pytest

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.rag.vector_store import InMemoryVectorStore, VectorEntry


def test_payload_validation_missing_fields() -> None:
    store = InMemoryVectorStore()
    entry = VectorEntry(vector=[0.1], payload={"kb_id": "kb_1"})
    with pytest.raises(AppError) as exc_info:
        store.upsert(kb_id="kb_1", entries=[entry])
    assert exc_info.value.code == ErrorCode.RAG_PAYLOAD_INVALID
