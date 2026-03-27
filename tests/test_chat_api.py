from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
import pytest

import app.api.v1.ask as ask_api
from app.auth.service import UserService
from app.core.settings import get_settings
from app.core.utils import utc_now_iso
from app.db.database import get_database, reset_database
from app.db.models import RoleRecord
from app.db.repos import RepositoryProvider
from app.main import app
from app.rag.chat_run_service import ChatRunService
from app.rag.next_steps import NEXT_STEP_ACTIONS
from app.rag.service import RagService
from tests.conftest import is_qdrant_available, is_qdrant_backend


@pytest.fixture(autouse=True)
def reset_store() -> None:
    reset_database(get_settings())


def test_conversation_crud_permissions() -> None:
    client = TestClient(app)
    admin_headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "会话权限知识库"}, headers=admin_headers).json()[
        "kb_id"
    ]
    _create_role_if_missing("viewer", ["conversation.read"])
    viewer = client.post(
        "/api/v1/users",
        json={"email": "viewer@example.com", "password": "User1234", "roles": ["viewer"]},
        headers=admin_headers,
    )
    assert viewer.status_code == 200
    user1 = client.post(
        "/api/v1/users",
        json={"email": "user1@example.com", "password": "User1234", "roles": ["user"]},
        headers=admin_headers,
    )
    assert user1.status_code == 200
    user2 = client.post(
        "/api/v1/users",
        json={"email": "user2@example.com", "password": "User1234", "roles": ["user"]},
        headers=admin_headers,
    )
    assert user2.status_code == 200

    viewer_headers = _login_headers(client, "viewer@example.com", "User1234")
    create_denied = client.post(
        "/api/v1/conversations",
        json={"kb_id": kb_id, "title": "viewer conv"},
        headers=viewer_headers,
    )
    assert create_denied.status_code == 403

    user1_headers = _login_headers(client, "user1@example.com", "User1234")
    created = client.post(
        "/api/v1/conversations",
        json={"kb_id": kb_id, "title": "u1 conv"},
        headers=user1_headers,
    )
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    user2_headers = _login_headers(client, "user2@example.com", "User1234")
    rename_forbidden = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "hacked"},
        headers=user2_headers,
    )
    assert rename_forbidden.status_code == 403

    renamed = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "u1 renamed"},
        headers=user1_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "u1 renamed"

    deleted = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=user1_headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_conversation_list_and_message_pagination() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "分页知识库"}, headers=headers).json()["kb_id"]
    ask1 = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "第一页问题"},
        headers=headers,
    )
    assert ask1.status_code == 200
    conversation_id = ask1.json()["conversation_id"]
    for text in ["第二页问题", "第三页问题", "第四页问题"]:
        response = client.post(
            f"/api/v1/kb/{kb_id}/ask",
            json={"question": text, "conversation_id": conversation_id},
            headers=headers,
        )
        assert response.status_code == 200

    listed = client.get("/api/v1/conversations?limit=1", headers=headers)
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["total"] >= 1
    assert len(listed_payload["items"]) == 1
    first_item = listed_payload["items"][0]
    assert "last_message_preview" in first_item
    assert "last_message_at" in first_item

    page1 = client.get(
        f"/api/v1/conversations/{conversation_id}/messages?limit=2",
        headers=headers,
    )
    assert page1.status_code == 200
    payload1 = page1.json()
    assert len(payload1["items"]) == 2
    assert payload1["has_more"] is True
    assert payload1["next_before"]

    page2 = client.get(
        f"/api/v1/conversations/{conversation_id}/messages?limit=2&before={payload1['next_before']}",
        headers=headers,
    )
    assert page2.status_code == 200
    payload2 = page2.json()
    assert len(payload2["items"]) == 2
    ids1 = {item["message_id"] for item in payload1["items"]}
    ids2 = {item["message_id"] for item in payload2["items"]}
    assert ids1.isdisjoint(ids2)


def test_stream_sse_events_and_request_id_consistency() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "SSE知识库", "config": _kb_config(topk=3, threshold=0.0)},
        headers=headers,
    ).json()["kb_id"]
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={"file": ("evidence.pdf", "补考 申请 条件 说明".encode("utf-8"), "application/pdf")},
        data={"source_uri": "https://example.edu/academic/policy"},
        headers=headers,
    )
    assert upload.status_code == 200
    _wait_for_job(client, upload.json()["job"]["job_id"], headers)

    with client.stream(
        "POST",
        f"/api/v1/kb/{kb_id}/ask/stream",
        headers=headers,
        json={"question": "补考申请条件是什么？"},
    ) as response:
        assert response.status_code == 200
        sse_events = _collect_sse_events(response)
    assert sse_events
    request_ids = {event[1]["request_id"] for event in sse_events if "request_id" in event[1]}
    assert len(request_ids) == 1
    event_names = [item[0] for item in sse_events]
    assert event_names[0] == "start"
    assert "token" in event_names
    assert "citation" in event_names
    assert event_names[-1] == "done"
    citation_payload = next(payload for event_name, payload in sse_events if event_name == "citation")
    assert citation_payload["citation"]["source_uri"] == "https://example.edu/academic/policy"


def test_stream_refusal_event_contains_next_steps() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "拒答SSE知识库"}, headers=headers).json()["kb_id"]

    with client.stream(
        "POST",
        f"/api/v1/kb/{kb_id}/ask/stream",
        headers=headers,
        json={"question": "补考申请条件是什么？"},
    ) as response:
        assert response.status_code == 200
        sse_events = _collect_sse_events(response)

    refusal_events = [payload for event_name, payload in sse_events if event_name == "refusal"]
    if is_qdrant_backend() and not is_qdrant_available():
        assert refusal_events == []
        return
    assert refusal_events
    refusal_payload = refusal_events[0]
    assert refusal_payload["refusal_reason"] in {
        "NO_EVIDENCE",
        "LOW_SCORE",
        "LOW_EVIDENCE",
        "LOW_COVERAGE",
    }
    assert refusal_payload["suggestions"]
    assert refusal_payload["next_steps"]
    assert refusal_payload["next_steps"][0]["action"] in NEXT_STEP_ACTIONS


def test_stream_cancel_and_run_cancel_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow_chunks(self, text: str, chunk_size: int = 24):
        del chunk_size
        for char in text:
            time.sleep(0.002)
            yield char

    check_state = {"count": 0}

    def _cancel_after_start(self, run_id: str) -> bool:
        del self, run_id
        check_state["count"] += 1
        return check_state["count"] >= 3

    monkeypatch.setattr(RagService, "_stream_text_chunks", _slow_chunks)
    monkeypatch.setattr(ChatRunService, "is_canceled", _cancel_after_start)
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "取消知识库", "config": _kb_config(topk=3, threshold=0.0)},
        headers=headers,
    ).json()["kb_id"]
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={
            "file": (
                "long.pdf",
                ("补考 条件 " * 120).encode("utf-8"),
                "application/pdf",
            )
        },
        headers=headers,
    )
    assert upload.status_code == 200
    _wait_for_job(client, upload.json()["job"]["job_id"], headers)

    with client.stream(
        "POST",
        f"/api/v1/kb/{kb_id}/ask/stream",
        headers=headers,
        json={"question": "补考条件是什么？"},
    ) as response:
        assert response.status_code == 200
        current_event = None
        for raw in response.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
                continue
            if not line.startswith("data: "):
                continue
            data = json.loads(line.removeprefix("data: ").strip())
            if current_event == "done":
                assert data["status"] == "canceled"
                assert data["run_id"]
                break


def test_cancel_endpoint_updates_run_status() -> None:
    client = TestClient(app)
    admin_headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "运行权限知识库"},
        headers=admin_headers,
    ).json()["kb_id"]
    user1 = client.post(
        "/api/v1/users",
        json={"email": "run_user1@example.com", "password": "User1234", "roles": ["user"]},
        headers=admin_headers,
    )
    assert user1.status_code == 200
    user2 = client.post(
        "/api/v1/users",
        json={"email": "run_user2@example.com", "password": "User1234", "roles": ["user"]},
        headers=admin_headers,
    )
    assert user2.status_code == 200
    user1_headers = _login_headers(client, "run_user1@example.com", "User1234")
    user2_headers = _login_headers(client, "run_user2@example.com", "User1234")
    user1_id = _current_user_id(client, user1_headers)

    run_service = ChatRunService(
        RepositoryProvider(get_database(get_settings())).chat_run()
    )
    run = run_service.create_run(
        request_id="req_cancel_test",
        kb_id=kb_id,
        user_id=user1_id,
        conversation_id=None,
    )

    forbidden_get = client.get(f"/api/v1/chat/runs/{run.run_id}", headers=user2_headers)
    assert forbidden_get.status_code == 403
    forbidden_cancel = client.post(f"/api/v1/chat/runs/{run.run_id}/cancel", headers=user2_headers)
    assert forbidden_cancel.status_code == 403

    run_detail = client.get(f"/api/v1/chat/runs/{run.run_id}", headers=user1_headers)
    assert run_detail.status_code == 200
    detail_payload = run_detail.json()
    assert detail_payload["run_id"] == run.run_id
    assert detail_payload["kb_id"] == kb_id
    assert detail_payload["status"] == "running"

    response = client.post(f"/api/v1/chat/runs/{run.run_id}/cancel", headers=user1_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run.run_id
    assert payload["cancel_flag"] is True
    assert payload["status"] == "canceled"


def test_regenerate_and_edit_resend_and_request_id() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "重生知识库", "config": _kb_config(topk=3, threshold=0.0)},
        headers=headers,
    ).json()["kb_id"]
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={"file": ("regen.pdf", "补考 申请 条件".encode("utf-8"), "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 200
    _wait_for_job(client, upload.json()["job"]["job_id"], headers)

    ask_response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "补考申请条件是什么？"},
        headers=headers,
    )
    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert ask_payload["request_id"]
    assert ask_response.headers["X-Request-ID"] == ask_payload["request_id"]

    regenerate = client.post(
        f"/api/v1/messages/{ask_payload['message_id']}/regenerate",
        json={},
        headers=headers,
    )
    assert regenerate.status_code == 200
    regenerate_payload = regenerate.json()
    assert regenerate_payload["conversation_id"] == ask_payload["conversation_id"]
    assert regenerate_payload["user_message_id"] == ask_payload["user_message_id"]
    assert regenerate_payload["message_id"] != ask_payload["message_id"]
    assert regenerate_payload["assistant_created_at"] is not None

    edit_resend = client.post(
        f"/api/v1/messages/{ask_payload['message_id']}/edit-and-resend",
        json={"question": "编辑后的问题：补考申请条件"},
        headers=headers,
    )
    assert edit_resend.status_code == 200
    edit_payload = edit_resend.json()
    assert edit_payload["conversation_id"] != ask_payload["conversation_id"]
    assert edit_payload["user_message_id"]

    failed = client.post(
        "/api/v1/kb/kb_missing/ask",
        json={"question": "测试失败请求"},
        headers=headers,
    )
    assert failed.status_code == 404
    failed_payload = failed.json()
    assert failed_payload["request_id"]
    assert failed.headers["X-Request-ID"] == failed_payload["request_id"]


def test_stream_supports_ping_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow_stream(self, **kwargs):
        del self
        run_id = kwargs["run_id"]
        request_id = kwargs["request_id"]
        yield {
            "event": "start",
            "data": {
                "run_id": run_id,
                "conversation_id": kwargs.get("conversation_id"),
                "request_id": request_id,
            },
        }
        time.sleep(0.03)
        yield {
            "event": "done",
            "data": {
                "run_id": run_id,
                "status": "succeeded",
                "request_id": request_id,
            },
        }

    monkeypatch.setattr(RagService, "ask_stream", _slow_stream)
    monkeypatch.setattr(ask_api, "SSE_PING_INTERVAL_SECONDS", 0.005)

    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post("/api/v1/kb", json={"name": "心跳知识库"}, headers=headers).json()["kb_id"]
    with client.stream(
        "POST",
        f"/api/v1/kb/{kb_id}/ask/stream",
        headers=headers,
        json={"question": "测试心跳"},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse_events(response)
    event_names = [event_name for event_name, _ in events]
    assert "ping" in event_names
    assert event_names[-1] == "done"


def test_multiturn_clarification_then_answer() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "多轮澄清知识库", "config": _kb_config(topk=1, threshold=0.0)},
        headers=headers,
    ).json()["kb_id"]
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={"file": ("clarify.pdf", "补考 申请 条件".encode("utf-8"), "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 200
    _wait_for_job(client, upload.json()["job"]["job_id"], headers)

    first = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "这个怎么办"},
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["refusal"] is True
    assert any(step["action"] == "add_context" for step in first_payload["next_steps"])

    second = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={
            "question": "补考申请条件是什么？",
            "conversation_id": first_payload["conversation_id"],
        },
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert second.status_code == 503
        assert second.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["conversation_id"] == first_payload["conversation_id"]
    assert second_payload["refusal"] is False


def test_latest_question_adds_freshness_warning() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    kb_id = client.post(
        "/api/v1/kb",
        json={"name": "时效提示知识库", "config": _kb_config(topk=1, threshold=0.0)},
        headers=headers,
    ).json()["kb_id"]
    upload = client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={"file": ("freshness.pdf", "补考 申请 条件".encode("utf-8"), "application/pdf")},
        data={
            "published_at": "2020-01-01",
            "source_uri": "https://example.edu/academic/policy",
        },
        headers=headers,
    )
    assert upload.status_code == 200
    _wait_for_job(client, upload.json()["job"]["job_id"], headers)

    response = client.post(
        f"/api/v1/kb/{kb_id}/ask",
        json={"question": "最新补考申请条件是什么？"},
        headers=headers,
    )
    if is_qdrant_backend() and not is_qdrant_available():
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "VECTOR_SEARCH_FAILED"
        return
    assert response.status_code == 200
    payload = response.json()
    assert payload["refusal"] is False
    assert "提示：问题涉及时效" in payload["answer"]
    assert payload["suggestions"]
    assert any(step["action"] == "check_official_source" for step in payload["next_steps"])


def _collect_sse_events(response) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    current_event = ""
    for raw in response.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ").strip()
            continue
        if line.startswith("data: "):
            data = json.loads(line.removeprefix("data: ").strip())
            events.append((current_event, data))
            if current_event == "done":
                break
    return events


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
    return _login_headers(client, "admin@example.com", "Admin1234")


def _current_user_id(client: TestClient, headers: dict[str, str]) -> str:
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    return response.json()["user_id"]


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_role_if_missing(name: str, permissions: list[str]) -> None:
    settings = get_settings()
    provider = RepositoryProvider(get_database(settings))
    if provider.role().get_by_name(name):
        return
    provider.role().create(
        RoleRecord(
            role_id=f"role_{name}",
            name=name,
            permissions_json=json.dumps(permissions, ensure_ascii=False),
            created_at=utc_now_iso(),
        )
    )


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


def _kb_config(topk: int, threshold: float) -> dict[str, object]:
    return {
        "topk": topk,
        "threshold": threshold,
        "rerank_enabled": False,
        "max_context_tokens": 3000,
        "min_evidence_chunks": 1,
        "min_context_chars": 1,
        "min_keyword_coverage": 0.0,
    }
