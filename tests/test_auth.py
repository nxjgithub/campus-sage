from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.service import UserService
from app.core.settings import get_settings
from app.db.database import get_database
from app.db.repos import RepositoryProvider
from app.main import app


def test_login_refresh_logout_flow() -> None:
    client = TestClient(app)
    _create_admin_user()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin1234"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["access_token"]
    assert payload["refresh_token"]

    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": payload["refresh_token"]},
    )
    assert refresh.status_code == 200
    refreshed = refresh.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout.status_code == 200

    refresh_again = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert refresh_again.status_code == 401


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
