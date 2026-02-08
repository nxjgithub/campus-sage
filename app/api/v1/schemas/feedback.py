"""反馈相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class FeedbackCreateRequest(BaseModel):
    """创建反馈请求。"""

    rating: Literal["up", "down"] = Field(description="反馈评分")
    reasons: list[str] = Field(default_factory=list, description="反馈原因")
    comment: str | None = Field(default=None, description="补充说明")
    expected_hint: str | None = Field(default=None, description="期望答案提示")


class FeedbackResponse(RequestIdMixin):
    """反馈响应。"""

    feedback_id: str = Field(description="反馈ID")
    message_id: str = Field(description="消息ID")
    status: str = Field(description="反馈状态")
