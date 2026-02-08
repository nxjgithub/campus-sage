"""会话记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationRecord:
    """会话记录。"""

    conversation_id: str
    kb_id: str
    title: str | None
    created_at: str
    updated_at: str
    deleted: bool
