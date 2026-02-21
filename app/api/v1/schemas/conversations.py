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
    last_message_preview: str | None = Field(default=None, description="最后一条消息摘要")
    last_message_at: str | None = Field(default=None, description="最后一条消息时间")
    updated_at: str = Field(description="更新时间")


class ConversationListResponse(RequestIdMixin):
    """会话列表响应。"""

    items: list[ConversationListItem] = Field(description="会话列表")
    total: int = Field(default=0, description="会话总数")
    next_cursor: str | None = Field(default=None, description="下一页游标")


class ConversationCreateRequest(BaseModel):
    """创建会话请求。"""

    kb_id: str = Field(description="知识库ID")
    title: str | None = Field(default=None, description="会话标题")


class ConversationCreateResponse(RequestIdMixin):
    """创建会话响应。"""

    conversation_id: str = Field(description="会话ID")
    kb_id: str = Field(description="知识库ID")
    title: str | None = Field(default=None, description="会话标题")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class ConversationRenameRequest(BaseModel):
    """重命名会话请求。"""

    title: str | None = Field(default=None, description="会话标题")


class ConversationDeleteResponse(RequestIdMixin):
    """删除会话响应。"""

    conversation_id: str = Field(description="会话ID")
    status: str = Field(description="删除状态")


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


class MessagePageResponse(RequestIdMixin):
    """消息分页响应。"""

    items: list[MessageItem] = Field(description="消息列表")
    has_more: bool = Field(description="是否还有更多")
    next_before: str | None = Field(default=None, description="下一页 before 游标")
