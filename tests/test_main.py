from __future__ import annotations

import pytest

from app.core.settings import reset_settings
from app.main import create_app


def test_create_app_rejects_weak_jwt_secret_in_prod(monkeypatch) -> None:
    """生产环境遇到弱 JWT 密钥时必须直接阻断启动。"""

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET_KEY", "short-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test-main.db")
    reset_settings()
    monkeypatch.setattr("app.main.init_database", lambda settings: None)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app()

    reset_settings()
