from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
import time

from app.core.settings import get_settings
from app.db.database import get_database, reset_database
from app.db.repos import RepositoryProvider
from app.main import app
from app.auth.service import UserService
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
    assert payload["citations"] == []


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
    files = {"file": ("demo.txt", b"dummy content", "text/plain")}
    response = client.post(
        f"/api/v1/kb/{kb_id}/documents", files=files, headers=headers
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


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
    assert payload["refusal"] is False
    assert payload["citations"]
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
