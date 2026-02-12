from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RefreshTokenRecord:
    """刷新令牌记录。"""

    token_id: str
    user_id: str
    token_hash: str
    expires_at: str
    revoked: bool
    created_at: str
    revoked_at: str | None
