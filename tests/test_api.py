from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest
import time

from app.core.settings import get_settings
from app.db.database import get_database, reset_database
from app.db.repos import RepositoryProvider
from app.main import app
from app.auth.service import UserService
from app.rag.next_steps import NEXT_STEP_ACTIONS
from tests.conftest import is_qdrant_available, is_qdrant_backend, is_redis_available


@pytest.fixture(autouse=True)
def reset_store() -> None:
    reset_database(get_settings())


def test_create_and_list_kb() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.post("/api/v1/kb", json={"name": "教务知识库"}, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    kb_id = payload["kb_id"]
    assert payload["request_id"]
    assert payload["config"]["topk"] == 5

    list_response = client.get("/api/v1/kb", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert any(item["kb_id"] == kb_id for item in items)

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
    assert assistant_message["next_steps"]
    assert assistant_message["next_steps"][0]["action"] in NEXT_STEP_ACTIONS

    page_response = client.get(
        f"/api/v1/conversations/{payload['conversation_id']}/messages?limit=10",
        headers=headers,
    )
    assert page_response.status_code == 200
    page_payload = page_response.json()
    paged_assistant = [item for item in page_payload["items"] if item["role"] == "assistant"]
    assert paged_assistant
    assert paged_assistant[-1]["next_steps"]


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


def test_ask_with_evidence() -> None:
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


def test_conversation_and_feedback_flow() -> None:
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
