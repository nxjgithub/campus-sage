"""会话记忆记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationMemoryRecord:
    """会话轻量记忆记录。"""

    conversation_id: str
    summary: str | None
    anchor_question: str | None
    slots: dict[str, str]
    recent_user_questions: list[str]
    updated_at: str
