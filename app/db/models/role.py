from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RoleRecord:
    """角色记录。"""

    role_id: str
    name: str
    permissions_json: str
    created_at: str
