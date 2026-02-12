from __future__ import annotations

from dataclasses import dataclass

from app.db.models import UserRecord


@dataclass(slots=True)
class TokenPair:
    """访问与刷新令牌。"""

    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(slots=True)
class CurrentUser:
    """当前用户信息（包含权限集）。"""

    user: UserRecord
    roles: list[str]
    permissions: set[str]
