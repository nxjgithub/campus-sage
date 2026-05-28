from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.auth.service import UserService
from app.core.settings import get_settings
from app.db.database import get_database, reset_database
from app.db.repos import RepositoryProvider
from app.main import app


@pytest.fixture(autouse=True)
def reset_store() -> None:
    reset_database(get_settings())


def test_kb_visibility_matrix_for_guest_user_manager_and_admin() -> None:
    client = TestClient(app)
    admin_headers = _create_and_login(client, "admin@example.com", "Admin1234", ["admin"])
    user_headers = _create_and_login(client, "user@example.com", "User1234", ["user"])
    manager_headers = _create_and_login(client, "manager@example.com", "Manager1234", ["manager"])

    public_id = _create_kb(client, admin_headers, "公开知识库", "public")
    internal_id = _create_kb(client, admin_headers, "内部知识库", "internal")
    admin_id = _create_kb(client, admin_headers, "管理员知识库", "admin")

    guest_items = client.get("/api/v1/kb").json()["items"]
    assert _visible_names(guest_items) == {"公开知识库"}

    user_items = client.get("/api/v1/kb", headers=user_headers).json()["items"]
    assert _visible_names(user_items) == {"公开知识库", "内部知识库"}

    manager_items = client.get("/api/v1/kb", headers=manager_headers).json()["items"]
    assert _visible_names(manager_items) == {"公开知识库", "内部知识库"}

    admin_items = client.get("/api/v1/kb", headers=admin_headers).json()["items"]
    assert _visible_names(admin_items) == {"公开知识库", "内部知识库", "管理员知识库"}

    assert client.get(f"/api/v1/kb/{public_id}").status_code == 401
    assert client.post(f"/api/v1/kb/{public_id}/ask", json={"question": "测试"}).status_code == 200
    assert client.post(f"/api/v1/kb/{internal_id}/ask", json={"question": "测试"}).status_code == 401
    assert client.post(f"/api/v1/kb/{admin_id}/ask", json={"question": "测试"}).status_code == 401

    assert client.get(f"/api/v1/kb/{admin_id}", headers=user_headers).status_code == 403
    assert client.get(f"/api/v1/kb/{admin_id}", headers=manager_headers).status_code == 403
    assert client.get(f"/api/v1/kb/{admin_id}", headers=admin_headers).status_code == 200


def test_kb_access_does_not_bypass_admin_visibility() -> None:
    client = TestClient(app)
    admin_headers = _create_and_login(client, "admin@example.com", "Admin1234", ["admin"])
    user_headers = _create_and_login(client, "user@example.com", "User1234", ["user"])
    user_id = client.get("/api/v1/users/me", headers=user_headers).json()["user_id"]
    admin_id = _create_kb(client, admin_headers, "管理员知识库", "admin")

    service = _user_service()
    service.upsert_kb_access(user_id, admin_id, "admin")

    response = client.get(f"/api/v1/kb/{admin_id}", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "KB_ACCESS_DENIED"


def test_manager_can_manage_public_and_internal_but_not_admin_kb() -> None:
    client = TestClient(app)
    admin_headers = _create_and_login(client, "admin@example.com", "Admin1234", ["admin"])
    manager_headers = _create_and_login(client, "manager@example.com", "Manager1234", ["manager"])
    internal_id = _create_kb(client, admin_headers, "内部知识库", "internal")
    admin_id = _create_kb(client, admin_headers, "管理员知识库", "admin")

    create_admin_response = client.post(
        "/api/v1/kb",
        json={"name": "经理创建管理员知识库", "visibility": "admin"},
        headers=manager_headers,
    )
    assert create_admin_response.status_code == 403

    create_internal_response = client.post(
        "/api/v1/kb",
        json={"name": "经理创建内部知识库", "visibility": "internal"},
        headers=manager_headers,
    )
    assert create_internal_response.status_code == 200

    update_internal_response = client.patch(
        f"/api/v1/kb/{internal_id}",
        json={"description": "经理可维护内部知识库"},
        headers=manager_headers,
    )
    assert update_internal_response.status_code == 200

    update_to_admin_response = client.patch(
        f"/api/v1/kb/{internal_id}",
        json={"visibility": "admin"},
        headers=manager_headers,
    )
    assert update_to_admin_response.status_code == 403

    update_admin_response = client.patch(
        f"/api/v1/kb/{admin_id}",
        json={"description": "经理不可维护管理员知识库"},
        headers=manager_headers,
    )
    assert update_admin_response.status_code == 403


def _create_and_login(
    client: TestClient,
    email: str,
    password: str,
    roles: list[str],
) -> dict[str, str]:
    service = _user_service()
    service.ensure_roles_seeded()
    provider = RepositoryProvider(get_database(get_settings()))
    if provider.user().get_by_email(email) is None:
        service.create_user(email, password, roles)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_kb(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    visibility: str,
) -> str:
    response = client.post(
        "/api/v1/kb",
        json={"name": name, "visibility": visibility},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["kb_id"]


def _visible_names(items: list[dict[str, object]]) -> set[str]:
    return {str(item["name"]) for item in items}


def _user_service() -> UserService:
    settings = get_settings()
    provider = RepositoryProvider(get_database(settings))
    return UserService(provider.user(), provider.role(), provider.kb_access(), settings)
