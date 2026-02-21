"""聊天运行记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChatRunRecord:
    """流式聊天运行记录。"""

    run_id: str
    kb_id: str | None
    user_id: str | None
    conversation_id: str | None
    user_message_id: str | None
    assistant_message_id: str | None
    status: str
    cancel_flag: bool
    started_at: str
    finished_at: str | None
    request_id: str | None
