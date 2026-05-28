from __future__ import annotations

import base64
import io
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi.testclient import TestClient
import pytest
import time

from app.core.settings import get_settings, reset_settings
from app.core.utils import new_id, utc_now_iso
from app.db.database import get_database, reset_database
from app.db.migrations import LATEST_SCHEMA_VERSION
from app.db.models import ConversationRecord, MessageRecord
from app.db.repos import RepositoryProvider
from app.main import app
from app.auth.service import UserService
from app.rag.llm_client import VllmClient
from app.rag.next_steps import NEXT_STEP_ACTIONS
from tests.conftest import is_qdrant_available, is_qdrant_backend, is_redis_available


@pytest.fixture(autouse=True)
def reset_store() -> None:
    reset_database(get_settings())


def test_create_and_list_kb() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/kb",
        json={
            "name": "教务知识库",
            "description": "选课与考试制度",
            "config": {
                "topk": 7,
                "threshold": 0.2,
                "rerank_enabled": True,
                "max_context_tokens": 4096,
                "min_evidence_chunks": 1,
                "min_context_chars": 20,
                "min_keyword_coverage": 0.3,
            },
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    kb_id = payload["kb_id"]
    assert payload["request_id"]
    assert payload["config"]["topk"] == 7

    list_response = client.get("/api/v1/kb", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    listed_item = next(item for item in items if item["kb_id"] == kb_id)
    assert listed_item["description"] == "选课与考试制度"
    assert listed_item["config"]["topk"] == 7
    assert listed_item["config"]["threshold"] == 0.2
    assert listed_item["config"]["rerank_enabled"] is True

    duplicate = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "KB_ALREADY_EXISTS"


def test_patch_kb_config_partial_merge() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    create_response = client.post(
        "/api/v1/kb", json={"name": "配置更新知识库"}, headers=headers
    )
    assert create_response.status_code == 200
    kb_payload = create_response.json()
    kb_id = kb_payload["kb_id"]
    original_config = kb_payload["config"]

    patch_response = client.patch(
        f"/api/v1/kb/{kb_id}",
        json={"config": {"threshold": 0.22}},
        headers=headers,
    )
    assert patch_response.status_code == 200
    updated_config = patch_response.json()["config"]

    assert updated_config["threshold"] == 0.22
    assert updated_config["topk"] == original_config["topk"]
    assert updated_config["rerank_enabled"] == original_config["rerank_enabled"]
    assert (
        updated_config["max_context_tokens"] == original_config["max_context_tokens"]
    )
    assert (
        updated_config["min_evidence_chunks"] == original_config["min_evidence_chunks"]
    )
    assert updated_config["min_context_chars"] == original_config["min_context_chars"]
    assert (
        updated_config["min_keyword_coverage"]
        == original_config["min_keyword_coverage"]
    )


def test_patch_kb_config_rejects_invalid_merged_values() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    create_response = client.post("/api/v1/kb", json={"name": "参数校验知识库"}, headers=headers)
    assert create_response.status_code == 200
    kb_id = create_response.json()["kb_id"]

    patch_response = client.patch(
        f"/api/v1/kb/{kb_id}",
        json={"config": {"min_evidence_chunks": 999}},
        headers=headers,
    )
    assert patch_response.status_code == 400
    payload = patch_response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"
    assert payload["error"]["detail"]["field"] == "min_evidence_chunks"
    assert payload["error"]["detail"]["reason"] == "must_not_exceed_topk"


def test_create_kb_config_rejects_out_of_range_threshold() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/kb",
        json={
            "name": "阈值非法知识库",
            "config": {
                "topk": 5,
                "threshold": 1.1,
                "rerank_enabled": False,
                "max_context_tokens": 3000,
            },
        },
        headers=headers,
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"


def test_ask_refusal_when_no_evidence() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请需要什么条件？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    assert payload["refusal"] is True
    assert payload["refusal_reason"] in {
        "NO_EVIDENCE",
        "LOW_SCORE",
        "LOW_EVIDENCE",
        "LOW_COVERAGE",
    }
    assert payload["suggestions"]
    assert payload["next_steps"]
    assert payload["next_steps"][0]["action"]
    assert payload["next_steps"][0]["label"]
    assert payload["next_steps"][0]["detail"]
    assert payload["next_steps"][0]["action"] in NEXT_STEP_ACTIONS
    assert payload["citations"] == []


def test_conversation_detail_persists_refusal_next_steps() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "拒答会话知识库"}, headers=headers).json()[
        "kb_id"
    ]
    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请需要什么条件？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    assert payload["refusal"] is True

    detail_response = client.get(
        f"/api/v1/conversations/{payload['conversation_id']}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assistant_messages = [
        item for item in detail_payload["messages"] if item["role"] == "assistant"
    ]
    assert assistant_messages
    assistant_message = assistant_messages[-1]
    assert assistant_message["refusal"] is True
    assert assistant_message["refusal_reason"] == payload["refusal_reason"]
    assert assistant_message["suggestions"] == payload["suggestions"]
    assert assistant_message["next_steps"]
    assert assistant_message["next_steps"][0]["action"] in NEXT_STEP_ACTIONS
    assert assistant_message["request_id"] == payload["request_id"]

    page_response = client.get(
        f"/api/v1/conversations/{payload['conversation_id']}/messages?limit=10",
        headers=headers,
    )
    assert page_response.status_code == 200
    page_payload = page_response.json()
    paged_assistant = [item for item in page_payload["items"] if item["role"] == "assistant"]
    assert paged_assistant
    assert paged_assistant[-1]["suggestions"] == payload["suggestions"]
    assert paged_assistant[-1]["next_steps"]
    assert paged_assistant[-1]["request_id"] == payload["request_id"]


def test_ask_with_legacy_invalid_kb_config_fallback() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "旧配置知识库"}, headers=headers).json()[
        "kb_id"
    ]
    provider = RepositoryProvider(get_database(get_settings()))
    kb_repo = provider.knowledge_base()
    record = kb_repo.get(kb_id)
    assert record is not None
    record.config = {
        "topk": "abc",
        "threshold": "bad",
        "rerank_enabled": "not_bool",
        "max_context_tokens": -1,
        "min_evidence_chunks": 9999,
        "min_context_chars": "x",
        "min_keyword_coverage": 9,
    }
    kb_repo.update(record)

    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请需要什么条件？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    assert payload["refusal"] is True
    assert payload["refusal_reason"] in {
        "NO_EVIDENCE",
        "LOW_SCORE",
        "LOW_EVIDENCE",
        "LOW_COVERAGE",
    }
    assert payload["next_steps"]


def test_ask_rejects_invalid_runtime_topk() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "问答参数知识库"}, headers=headers).json()[
        "kb_id"
    ]
    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "测试问题", "topk": 0},
        headers=headers,
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"


def test_ask_rejects_invalid_runtime_threshold() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "问答参数知识库2"}, headers=headers).json()[
        "kb_id"
    ]
    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "测试问题", "threshold": 1.2},
        headers=headers,
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"


def test_ask_kb_not_found() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/kb/kb_missing/ask", json={"question": "测试问题"}, headers=headers
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "KB_NOT_FOUND"


def test_upload_document() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("demo.pdf", b"dummy content", "application/pdf")}
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["doc"]["status"] in {"processing", "indexed", "failed"}
    assert payload["job"]["status"] in {"queued", "running", "succeeded", "failed"}

    job_id = payload["job"]["job_id"]
    doc_id = payload["doc"]["doc_id"]
    _wait_for_job(client, job_id, headers)

    delete_response = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert delete_response.status_code == 200

    job_after_delete = client.get(f"/api/v1/ingest/jobs/{job_id}", headers=headers)
    assert job_after_delete.status_code == 404
    assert job_after_delete.json()["error"]["code"] == "INGEST_JOB_NOT_FOUND"


def test_upload_document_invalid_extension() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("demo.exe", b"dummy content", "application/octet-stream")}
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_upload_document_rejects_invalid_source_uri() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "来源链接知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("demo.pdf", b"dummy content", "application/pdf")}
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files=files,
        data={"source_uri": "javascript:alert(1)"},
        headers=headers,
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"
    assert payload["error"]["detail"]["field"] == "source_uri"


def test_upload_document_txt() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "文本知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("demo.txt", "补考申请条件".encode("utf-8"), "text/plain")}
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["doc"]["status"] in {"processing", "indexed", "failed"}
    assert payload["job"]["status"] in {"queued", "running", "succeeded", "failed"}


def test_upload_document_docx() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "Docx知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {
        "file": (
            "demo.docx",
            _build_docx_bytes(["补考申请流程", "学生需在规定时间内提交申请。"]),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["doc"]["status"] in {"processing", "indexed", "failed"}
    assert payload["job"]["status"] in {"queued", "running", "succeeded", "failed"}


def test_staged_document_preview_and_commit_docx_image() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "预览知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {
        "file": (
            "notice.docx",
            _build_docx_with_image_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    staged_response = client.post(
        f"/api/v1/kb/{kb_id}/documents/staged", files=files, headers=headers
    )
    assert staged_response.status_code == 200
    staged_id = staged_response.json()["staged_doc_id"]

    preview_response = client.post(
        f"/api/v1/staged-documents/{staged_id}/preview", headers=headers
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["assets"][0]["label"] == "图 1"
    block_types = [block["block_type"] for block in preview["preview_blocks"]]
    assert block_types[:3] == ["heading", "paragraph", "table"]
    assert "image" in block_types
    table_block = next(block for block in preview["preview_blocks"] if block["block_type"] == "table")
    assert table_block["rows"] == [["事项", "说明"], ["登录", "统一身份认证"]]
    image_chunk = next(chunk for chunk in preview["chunks"] if chunk.get("assets"))
    assert image_chunk["assets"][0]["asset_label"] == "图 1"
    update_response = client.patch(
        f"/api/v1/staged-documents/{staged_id}/chunks/{image_chunk['chunk_id']}",
        json={"enabled": False},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert any(
        chunk["chunk_id"] == image_chunk["chunk_id"] and not chunk["enabled"]
        for chunk in update_response.json()["chunks"]
    )
    reenable_response = client.patch(
        f"/api/v1/staged-documents/{staged_id}/chunks/{image_chunk['chunk_id']}",
        json={"enabled": True},
        headers=headers,
    )
    assert reenable_response.status_code == 200

    commit_response = client.post(
        f"/api/v1/staged-documents/{staged_id}/commit", headers=headers
    )
    assert commit_response.status_code == 200
    payload = commit_response.json()
    _wait_for_job(client, payload["job"]["job_id"], headers)
    detail = client.get(f"/api/v1/documents/{payload['doc']['doc_id']}", headers=headers).json()
    assert detail["status"] == "indexed"
    assert detail["chunk_count"] >= 1


def test_staged_document_preview_extracts_docx_image_with_bad_crc() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "坏CRC图片知识库"}, headers=headers).json()[
        "kb_id"
    ]
    docx_bytes = _build_docx_with_bad_crc_jpeg_bytes()
    with pytest.raises(BadZipFile):
        with ZipFile(io.BytesIO(docx_bytes)) as archive:
            archive.read("word/media/image1.jpeg")
    files = {
        "file": (
            "bad-crc-image.docx",
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    staged_response = client.post(
        f"/api/v1/kb/{kb_id}/documents/staged", files=files, headers=headers
    )
    assert staged_response.status_code == 200
    staged_id = staged_response.json()["staged_doc_id"]

    preview_response = client.post(
        f"/api/v1/staged-documents/{staged_id}/preview", headers=headers
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert len(preview["assets"]) == 1
    assert preview["assets"][0]["file_name"] == "image1.jpeg"
    assert any(block["block_type"] == "image" for block in preview["preview_blocks"])
    assert any(chunk.get("assets") for chunk in preview["chunks"])

    image_response = client.get(preview["assets"][0]["url"], headers=headers)
    assert image_response.status_code == 200
    assert image_response.content.startswith(b"\xff\xd8")


def test_upload_document_too_large() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    settings = get_settings()
    original_max_mb = settings.upload_max_mb
    settings.upload_max_mb = 1
    try:
        files = {"file": ("big.pdf", b"a" * (2 * 1024 * 1024), "application/pdf")}
        response = client.post(
            f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "FILE_TOO_LARGE"
    finally:
        settings.upload_max_mb = original_max_mb


def test_reindex_missing_file_marks_failed() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("demo.pdf", b"dummy content", "application/pdf")}
    upload = client.post(f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers)
    assert upload.status_code == 200
    payload = upload.json()
    doc_id = payload["doc"]["doc_id"]
    job_id = payload["job"]["job_id"]
    _wait_for_job(client, job_id, headers)

    storage_path = (
        Path(get_settings().storage_dir) / kb_id / f"{doc_id}.pdf"
    )
    storage_path.unlink(missing_ok=True)

    reindex = client.post(f"/api/v1/documents/{doc_id}/reindex", headers=headers)
    assert reindex.status_code == 200
    new_job_id = reindex.json()["job_id"]
    _wait_for_job(client, new_job_id, headers)
    job_detail = client.get(f"/api/v1/ingest/jobs/{new_job_id}", headers=headers)
    assert job_detail.status_code == 200
    job_payload = job_detail.json()
    assert job_payload["status"] == "failed"
    assert job_payload["error_code"] == "INGEST_PARSE_FAILED"


def test_ask_with_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_vllm(monkeypatch)
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_payload = {
        "name": "教务知识库",
        "config": {
            "topk": 1,
            "threshold": 0.0,
            "rerank_enabled": False,
            "max_context_tokens": 3000,
        },
    }
    kb_id = client.post("/api/v1/kb", json=kb_payload, headers=headers).json()["kb_id"]
    files = {"file": ("demo.pdf", "补考 申请 条件".encode("utf-8"), "application/pdf")}
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files=files,
        data={"source_uri": "https://example.edu/academic/policy"},
        headers=headers,
    )
    assert upload.status_code == 200
    assert upload.json()["doc"]["source_uri"] == "https://example.edu/academic/policy"
    job_id = upload.json()["job"]["job_id"]
    _wait_for_job(client, job_id, headers)

    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请需要什么条件？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    assert payload["refusal"] is False
    assert payload["next_steps"] == []
    assert payload["citations"]
    assert payload["citations"][0]["source_uri"] == "https://example.edu/academic/policy"
    if is_qdrant_backend() and is_qdrant_available():
        import os
        from qdrant_client import QdrantClient  # type: ignore

        base_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
        client = QdrantClient(url=base_url, check_compatibility=False)
        collections = {c.name for c in client.get_collections().collections}
        assert any(kb_id in name for name in collections)


def test_conversation_and_feedback_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_vllm(monkeypatch)
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_payload = {
        "name": "教务知识库",
        "config": {
            "topk": 1,
            "threshold": 0.0,
            "rerank_enabled": False,
            "max_context_tokens": 3000,
        },
    }
    kb_id = client.post("/api/v1/kb", json=kb_payload, headers=headers).json()["kb_id"]
    files = {"file": ("demo.pdf", "补考 申请 条件".encode("utf-8"), "application/pdf")}
    upload = client.post(f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers)
    assert upload.status_code == 200
    job_id = upload.json()["job"]["job_id"]
    _wait_for_job(client, job_id, headers)

    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请需要什么条件？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    conversation_id = payload["conversation_id"]
    message_id = payload["message_id"]
    assert conversation_id
    assert message_id

    list_response = client.get("/api/v1/conversations", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert any(item["conversation_id"] == conversation_id for item in items)

    detail_response = client.get(
        f"/api/v1/conversations/{conversation_id}", headers=headers
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["conversation_id"] == conversation_id
    assert detail["messages"]

    feedback_payload = {
        "rating": "down",
        "reasons": ["INCOMPLETE"],
        "comment": "信息不足",
    }
    feedback_response = client.post(
        f"/api/v1/messages/{message_id}/feedback",
        json=feedback_payload,
        headers=headers,
    )
    assert feedback_response.status_code == 200
    feedback = feedback_response.json()
    assert feedback["message_id"] == message_id


def test_monitor_queue_stats() -> None:
    if not is_redis_available():
        pytest.skip("Redis 不可用，跳过队列监控测试")
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.get("/api/v1/monitor/queues", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "stats" in payload
    assert "queued" in payload["stats"]
    assert "dead" in payload["stats"]


def test_monitor_runtime_diagnostics() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.get("/api/v1/monitor/runtime", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    settings = get_settings()
    assert payload["request_id"]
    assert payload["database"]["schema_version"] == LATEST_SCHEMA_VERSION
    assert payload["database"]["backend"] == settings.database_backend
    assert payload["database"]["target"] == settings.database_target
    assert payload["services"]["vector_backend"] == settings.vector_backend
    assert payload["services"]["embedding_backend"] == settings.embedding_backend
    assert payload["rag_metrics"]["sample_size"] >= 0
    assert "clarification_rate" in payload["rag_metrics"]
    assert "citation_coverage_rate" in payload["rag_metrics"]
    assert "pdf" in payload["upload"]["allowed_exts"]
    assert payload["security"]["jwt_default_secret"] is False
    assert payload["security"]["jwt_weak_secret"] is False


def test_monitor_runtime_rag_metrics_reflect_recent_messages() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "运行时指标知识库"},
        headers=headers,
    ).json()["kb_id"]

    provider = RepositoryProvider(get_database(get_settings()))
    conversation_id = new_id("conv")
    created_at = utc_now_iso()
    provider.conversation().create_conversation(
        ConversationRecord(
            conversation_id=conversation_id,
            kb_id=kb_id,
            user_id=None,
            title="运行时指标会话",
            created_at=created_at,
            updated_at=created_at,
            deleted=False,
        )
    )
    messages = [
        MessageRecord(
            message_id=new_id("msg"),
            conversation_id=conversation_id,
            role="assistant",
            content="请先补充学院和年级。",
            refusal=True,
            refusal_reason="LOW_COVERAGE",
            timing=None,
            suggestions=["建议补充学院和年级信息"],
            next_steps=[{"action": "add_context"}],
            citations=[],
            created_at=utc_now_iso(),
        ),
        MessageRecord(
            message_id=new_id("msg"),
            conversation_id=conversation_id,
            role="assistant",
            content="回答正文\n\n提示：问题涉及时效，请核验官方通知。",
            refusal=False,
            refusal_reason=None,
            timing=None,
            suggestions=[],
            next_steps=[{"action": "check_official_source"}],
            citations=[{"citation_id": 1, "doc_id": "doc_demo"}],
            created_at=utc_now_iso(),
        ),
        MessageRecord(
            message_id=new_id("msg"),
            conversation_id=conversation_id,
            role="assistant",
            content="这是一条无引用回答。",
            refusal=False,
            refusal_reason=None,
            timing=None,
            suggestions=[],
            next_steps=[],
            citations=[],
            created_at=utc_now_iso(),
        ),
    ]
    for item in messages:
        provider.conversation().create_message(item)

    response = client.get("/api/v1/monitor/runtime", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    metrics = payload["rag_metrics"]
    assert metrics["sample_size"] == 3
    assert metrics["refusal_count"] == 1
    assert metrics["clarification_count"] == 1
    assert metrics["freshness_warning_count"] == 1
    assert metrics["citation_covered_count"] == 1
    assert metrics["refusal_rate"] == 0.3333
    assert metrics["clarification_rate"] == 0.3333
    assert metrics["freshness_warning_rate"] == 0.3333
    assert metrics["citation_coverage_rate"] == 0.3333


def test_cancel_and_retry_job() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers).json()[
        "kb_id"
    ]
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    upload = client.post(f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers)
    assert upload.status_code == 200
    job_id = upload.json()["job"]["job_id"]
    _wait_for_job(client, job_id, headers)

    cancel = client.post(f"/api/v1/ingest/jobs/{job_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    cancel_status = cancel.json()["status"]
    assert cancel_status in {"failed", "canceled", "succeeded"}

    retry = client.post(f"/api/v1/ingest/jobs/{job_id}/retry", headers=headers)
    assert retry.status_code in {200, 409}
    if retry.status_code == 200:
        new_job_id = retry.json()["job_id"]
        assert new_job_id != job_id
        _wait_for_job(client, new_job_id, headers)
    else:
        assert retry.json()["error"]["code"] == "INGEST_JOB_NOT_RETRYABLE"


def _wait_for_job(client: TestClient, job_id: str, headers: dict[str, str]) -> None:
    deadline = time.time() + 2.0
    status = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/ingest/jobs/{job_id}", headers=headers)
        if response.status_code != 200:
            time.sleep(0.05)
            continue
        status = response.json()["status"]
        if status in {"succeeded", "failed"}:
            return
        time.sleep(0.05)
    if status in {"queued", "running"}:
        time.sleep(0.1)


def _enable_fake_vllm(monkeypatch: pytest.MonkeyPatch, answer: str = "模型基于证据生成回答。") -> None:
    """让正常回答测试显式经过模型客户端。"""

    def _fake_generate(self, question: str, context: str) -> str:
        del self, question, context
        return answer

    monkeypatch.setenv("VLLM_ENABLED", "true")
    monkeypatch.setattr(VllmClient, "generate", _fake_generate)
    reset_settings()


def _auth_headers(client: TestClient) -> dict[str, str]:
    _create_admin_user()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin1234"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_admin_user() -> None:
    settings = get_settings()
    provider = RepositoryProvider(get_database(settings))
    if provider.user().get_by_email("admin@example.com"):
        return
    service = UserService(
        provider.user(),
        provider.role(),
        provider.kb_access(),
        settings,
    )
    service.ensure_roles_seeded()
    service.create_user("admin@example.com", "Admin1234", ["admin"])


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        body = "".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
        archive.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
  </w:body>
</w:document>""",
        )
    return buffer.getvalue()


def _build_docx_with_image_bytes() -> bytes:
    """构造包含正文和内嵌图片的 DOCX 测试文件。"""

    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>自助打印终端操作指南</w:t></w:r></w:p>
    <w:p><w:r><w:t>微信扫码后使用统一身份认证登录。</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>事项</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>说明</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>登录</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>统一身份认证</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:p><w:r><w:drawing><a:blip r:embed="rId2"/></w:drawing></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr("word/media/image1.png", image_bytes)
    return buffer.getvalue()


def _build_docx_with_bad_crc_jpeg_bytes() -> bytes:
    """构造图片 CRC 错误但图片字节完整的 DOCX。"""

    image_bytes = b"\xff\xd8\xff\xe0" + (b"\x00" * 1024) + b"\xff\xd9"
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.jpeg"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p><w:r><w:t>保密知识竞赛</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><a:blip r:embed="rId2"/></w:drawing></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr("word/media/image1.jpeg", image_bytes)
    return _zero_zip_entry_crc(buffer.getvalue(), "word/media/image1.jpeg")


def _zero_zip_entry_crc(docx_bytes: bytes, entry_name: str) -> bytes:
    """把指定 ZIP 条目的 CRC 置零，用于模拟部分 Office 导出的异常文件。"""

    data = bytearray(docx_bytes)
    name = entry_name.encode("utf-8")
    local_name_index = data.find(name)
    assert local_name_index > 0
    local_header_index = data.rfind(b"PK\x03\x04", 0, local_name_index)
    assert local_header_index >= 0
    data[local_header_index + 14 : local_header_index + 18] = b"\x00\x00\x00\x00"

    central_name_index = data.find(name, local_name_index + len(name))
    assert central_name_index > 0
    central_header_index = data.rfind(b"PK\x01\x02", 0, central_name_index)
    assert central_header_index >= 0
    data[central_header_index + 16 : central_header_index + 20] = b"\x00\x00\x00\x00"
    return bytes(data)
