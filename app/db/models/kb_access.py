from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KbAccessRecord:
    """知识库访问权限记录。"""

    user_id: str
    kb_id: str
    access_level: str
    created_at: str
    updated_at: str
