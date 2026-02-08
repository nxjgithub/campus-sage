"""反馈记录模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FeedbackRecord:
    """反馈记录。"""

    feedback_id: str
    message_id: str
    rating: str
    reasons: list[str]
    comment: str | None
    expected_hint: str | None
    status: str
    created_at: str
