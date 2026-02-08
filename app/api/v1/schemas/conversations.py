"""会话相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin
from app.api.v1.schemas.rag import Citation


class ConversationListItem(BaseModel):
    """会话列表项。"""

    conversation_id: str = Field(description="会话ID")
    kb_id: str = Field(description="知识库ID")
    title: str | None = Field(default=None, description="会话标题")
    updated_at: str = Field(description="更新时间")


class ConversationListResponse(RequestIdMixin):
    """会话列表响应。"""

    items: list[ConversationListItem] = Field(description="会话列表")


class MessageItem(BaseModel):
    """消息条目。"""

    message_id: str = Field(description="消息ID")
    role: Literal["user", "assistant"] = Field(description="消息角色")
    content: str = Field(description="消息内容")
    citations: list[Citation] | None = Field(default=None, description="引用列表")
    refusal: bool | None = Field(default=None, description="是否拒答")
    refusal_reason: str | None = Field(default=None, description="拒答原因")
    timing: dict[str, int] | None = Field(default=None, description="耗时信息")
    created_at: str = Field(description="创建时间")


class ConversationDetailResponse(RequestIdMixin):
    """会话详情响应。"""

    conversation_id: str = Field(description="会话ID")
    kb_id: str = Field(description="知识库ID")
    messages: list[MessageItem] = Field(description="消息列表")
