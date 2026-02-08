"""消息记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MessageRecord:
    """消息记录。"""

    message_id: str
    conversation_id: str
    role: str
    content: str
    refusal: bool
    refusal_reason: str | None
    timing: dict[str, int] | None
    citations: list[dict[str, object]]
    created_at: str
