"""问答相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class AskFilters(BaseModel):
    """检索过滤条件。"""

    doc_ids: list[str] | None = Field(default=None, description="限定文档ID列表")
    published_after: str | None = Field(default=None, description="限定发布日期下限")


class AskRequest(BaseModel):
    """问答请求。"""

    question: str = Field(description="问题")
    conversation_id: str | None = Field(default=None, description="会话ID")
    topk: int | None = Field(default=None, description="TopK")
    threshold: float | None = Field(default=None, description="拒答阈值")
    rerank_enabled: bool | None = Field(default=None, description="是否启用重排")
    filters: AskFilters | None = Field(default=None, description="检索过滤条件")
    debug: bool = Field(default=False, description="是否开启调试")


class Citation(BaseModel):
    """引用条目。"""

    citation_id: int = Field(description="引用编号")
    doc_id: str = Field(description="文档ID")
    doc_name: str = Field(description="文档名称")
    doc_version: str | None = Field(default=None, description="文档版本")
    published_at: str | None = Field(default=None, description="发布日期")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    section_path: str | None = Field(default=None, description="章节路径")
    chunk_id: str = Field(description="分块ID")
    snippet: str = Field(description="引用片段")
    score: float | None = Field(default=None, description="相似度分数")


class AskResponse(RequestIdMixin):
    """问答响应。"""

    answer: str = Field(description="答案")
    refusal: bool = Field(description="是否拒答")
    refusal_reason: str | None = Field(default=None, description="拒答原因")
    suggestions: list[str] = Field(description="建议列表")
    citations: list[Citation] = Field(description="引用列表")
    conversation_id: str | None = Field(default=None, description="会话ID")
    message_id: str | None = Field(default=None, description="消息ID")
    timing: dict[str, int] | None = Field(default=None, description="耗时信息")
