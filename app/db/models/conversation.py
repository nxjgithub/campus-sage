"""会话记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationRecord:
    """会话记录。"""

    conversation_id: str
    kb_id: str
    user_id: str | None
    title: str | None
    created_at: str
    updated_at: str
    deleted: bool
    last_message_preview: str | None = None
    last_message_at: str | None = None
