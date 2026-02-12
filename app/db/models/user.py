from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UserRecord:
    """用户记录。"""

    user_id: str
    email: str
    password_hash: str
    status: str
    created_at: str
    updated_at: str
    last_login_at: str | None
