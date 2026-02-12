from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.auth.service import UserService
from app.core.settings import get_settings
from app.db.database import get_database, reset_database
from app.db.repos import RepositoryProvider
from app.main import app
from app.rag.embedding import get_embedder
from app.rag.vector_store import VectorEntry, get_vector_store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    reset_database(get_settings())


def test_list_roles() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.get("/api/v1/roles", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    names = {item["name"] for item in items}
    assert {"admin", "user"}.issubset(names)


def test_user_list_pagination_and_filter() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/users",
        json={"email": "user1@example.com", "password": "User1234", "roles": ["user"]},
        headers=headers,
    )
    assert created.status_code == 200
    user1_id = created.json()["user_id"]

    created2 = client.post(
        "/api/v1/users",
        json={"email": "user2@example.com", "password": "User1234", "roles": ["user"]},
        headers=headers,
    )
    assert created2.status_code == 200
    user2_id = created2.json()["user_id"]

    updated = client.patch(
        f"/api/v1/users/{user2_id}",
        json={"status": "disabled"},
        headers=headers,
    )
    assert updated.status_code == 200

    page = client.get("/api/v1/users?limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    payload = page.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["total"] >= 2
    assert len(payload["items"]) == 1

    filtered = client.get("/api/v1/users?status=disabled", headers=headers)
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    ids = {item["user_id"] for item in filtered_payload["items"]}
    assert user2_id in ids
    assert user1_id not in ids

    keyword = client.get("/api/v1/users?keyword=user1", headers=headers)
    assert keyword.status_code == 200
    keyword_payload = keyword.json()
    assert any(item["user_id"] == user1_id for item in keyword_payload["items"])


def test_kb_access_delete_and_bulk_update() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)

    user = client.post(
        "/api/v1/users",
        json={"email": "kbuser@example.com", "password": "User1234", "roles": ["user"]},
        headers=headers,
    )
    user_id = user.json()["user_id"]

    kb1 = client.post("/api/v1/kb", json={"name": "知识库A"}, headers=headers).json()[
        "kb_id"
    ]
    kb2 = client.post("/api/v1/kb", json={"name": "知识库B"}, headers=headers).json()[
        "kb_id"
    ]

    grant1 = client.post(
        f"/api/v1/users/{user_id}/kb-access",
        json={"kb_id": kb1, "access_level": "read"},
        headers=headers,
    )
    assert grant1.status_code == 200
    grant2 = client.post(
        f"/api/v1/users/{user_id}/kb-access",
        json={"kb_id": kb2, "access_level": "write"},
        headers=headers,
    )
    assert grant2.status_code == 200

    deleted = client.delete(
        f"/api/v1/users/{user_id}/kb-access/{kb1}", headers=headers
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    listed = client.get(f"/api/v1/users/{user_id}/kb-access", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert all(item["kb_id"] != kb1 for item in items)

    bulk = client.put(
        f"/api/v1/users/{user_id}/kb-access",
        json={
            "items": [
                {"kb_id": kb1, "access_level": "read"},
                {"kb_id": kb2, "access_level": "admin"},
            ]
        },
        headers=headers,
    )
    assert bulk.status_code == 200
    bulk_ids = {item["kb_id"] for item in bulk.json()["items"]}
    assert {kb1, kb2}.issubset(bulk_ids)


def test_eval_api_flow() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)

    kb_id = client.post("/api/v1/kb", json={"name": "评测知识库"}, headers=headers).json()[
        "kb_id"
    ]
    settings = get_settings()
    store = get_vector_store(settings)
    store.delete_by_kb_id(kb_id)
    embedder = get_embedder(settings)
    question = "补考 条件"
    vector = embedder.embed_query(question)
    payload = {
        "contract_version": "0.1",
        "kb_id": kb_id,
        "doc_id": "doc_eval",
        "doc_name": "eval.pdf",
        "doc_version": None,
        "published_at": "2025-01-01",
        "page_start": 1,
        "page_end": 1,
        "section_path": None,
        "chunk_id": "chunk_eval",
        "chunk_index": 0,
        "text": "补考 条件 说明",
    }
    store.upsert(kb_id=kb_id, entries=[VectorEntry(vector=vector, payload=payload)])

    eval_set = client.post(
        "/api/v1/eval/sets",
        json={
            "name": "评测集",
            "items": [
                {
                    "question": question,
                    "gold_doc_id": "doc_eval",
                    "gold_page_start": 1,
                    "gold_page_end": 1,
                }
            ],
        },
        headers=headers,
    )
    assert eval_set.status_code == 200
    eval_set_id = eval_set.json()["eval_set_id"]

    run = client.post(
        "/api/v1/eval/runs",
        json={"eval_set_id": eval_set_id, "kb_id": kb_id, "topk": 5},
        headers=headers,
    )
    assert run.status_code == 200
    run_payload = run.json()
    assert run_payload["metrics"]["samples"] == 1

    run_id = run_payload["run_id"]
    fetched = client.get(f"/api/v1/eval/runs/{run_id}", headers=headers)
    assert fetched.status_code == 200
    fetched_payload = fetched.json()
    assert fetched_payload["run_id"] == run_id


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
