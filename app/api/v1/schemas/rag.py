"""问答相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin
from app.rag.next_steps import NextStepAction


class AskFilters(BaseModel):
    """检索过滤条件。"""

    doc_ids: list[str] | None = Field(default=None, description="限定文档ID列表")
    published_after: str | None = Field(default=None, description="限定发布日期下限")


class AskRequest(BaseModel):
    """问答请求。"""

    question: str = Field(description="问题")
    conversation_id: str | None = Field(default=None, description="会话ID")
    topk: int | None = Field(default=None, ge=1, le=50, description="TopK")
    threshold: float | None = Field(default=None, ge=0, le=1, description="拒答阈值")
    rerank_enabled: bool | None = Field(default=None, description="是否启用重排")
    filters: AskFilters | None = Field(default=None, description="检索过滤条件")
    debug: bool = Field(default=False, description="是否开启调试")


class AskStreamRequest(AskRequest):
    """流式问答请求。"""


class RegenerateRequest(BaseModel):
    """重新生成请求。"""

    topk: int | None = Field(default=None, ge=1, le=50, description="TopK")
    threshold: float | None = Field(default=None, ge=0, le=1, description="拒答阈值")
    rerank_enabled: bool | None = Field(default=None, description="是否启用重排")
    filters: AskFilters | None = Field(default=None, description="检索过滤条件")
    debug: bool = Field(default=False, description="是否开启调试")


class EditAndResendRequest(RegenerateRequest):
    """编辑后重发请求。"""

    question: str = Field(description="编辑后的问题")


class Citation(BaseModel):
    """引用条目。"""

    citation_id: int = Field(description="引用编号")
    doc_id: str = Field(description="文档ID")
    doc_name: str = Field(description="文档名称")
    doc_version: str | None = Field(default=None, description="文档版本")
    published_at: str | None = Field(default=None, description="发布日期")
    source_uri: str | None = Field(default=None, description="文档官方来源链接")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    section_path: str | None = Field(default=None, description="章节路径")
    chunk_id: str = Field(description="分块ID")
    snippet: str = Field(description="引用片段")
    score: float | None = Field(default=None, description="相似度分数")


class NextStep(BaseModel):
    """拒答后的结构化下一步建议。"""

    action: NextStepAction = Field(description="建议动作类型")
    label: str = Field(description="建议标题")
    detail: str = Field(description="建议说明")
    value: str | None = Field(default=None, description="建议动作附带值")


class AskResponse(RequestIdMixin):
    """问答响应。"""

    answer: str = Field(description="答案")
    refusal: bool = Field(description="是否拒答")
    refusal_reason: str | None = Field(default=None, description="拒答原因")
    suggestions: list[str] = Field(description="建议列表")
    next_steps: list[NextStep] = Field(description="结构化下一步建议")
    citations: list[Citation] = Field(description="引用列表")
    conversation_id: str | None = Field(default=None, description="会话ID")
    message_id: str | None = Field(default=None, description="消息ID")
    user_message_id: str | None = Field(default=None, description="用户消息ID")
    assistant_created_at: str | None = Field(default=None, description="助手消息创建时间")
    timing: dict[str, int] | None = Field(default=None, description="耗时信息")


class ChatRunCancelResponse(RequestIdMixin):
    """取消聊天运行响应。"""

    run_id: str = Field(description="运行ID")
    status: str = Field(description="运行状态")
    cancel_flag: bool = Field(description="是否已取消")


class ChatRunResponse(RequestIdMixin):
    """聊天运行详情响应。"""

    run_id: str = Field(description="运行ID")
    kb_id: str | None = Field(default=None, description="知识库ID")
    conversation_id: str | None = Field(default=None, description="会话ID")
    user_message_id: str | None = Field(default=None, description="用户消息ID")
    assistant_message_id: str | None = Field(default=None, description="助手消息ID")
    status: str = Field(description="运行状态")
    cancel_flag: bool = Field(description="是否已取消")
    started_at: str = Field(description="开始时间")
    finished_at: str | None = Field(default=None, description="结束时间")
