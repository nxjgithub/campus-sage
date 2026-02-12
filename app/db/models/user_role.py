from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UserRoleRecord:
    """用户角色关联记录。"""

    user_id: str
    role_id: str
    created_at: str
