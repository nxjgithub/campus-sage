"""问答领域 DTO，避免依赖 API 层。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.rag.next_steps import NextStepAction


class CitationDTO(BaseModel):
    """内部引用结构。"""

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


class NextStepDTO(BaseModel):
    """拒答后的结构化下一步建议。"""

    action: NextStepAction = Field(description="建议动作类型")
    label: str = Field(description="建议标题")
    detail: str = Field(description="建议说明")
    value: str | None = Field(default=None, description="建议动作附带值")


class AskResult(BaseModel):
    """内部问答结果。"""

    answer: str = Field(description="答案")
    refusal: bool = Field(description="是否拒答")
    refusal_reason: str | None = Field(default=None, description="拒答原因")
    suggestions: list[str] = Field(description="建议列表")
    next_steps: list[NextStepDTO] = Field(description="结构化下一步建议")
    citations: list[CitationDTO] = Field(description="引用列表")
    conversation_id: str | None = Field(default=None, description="会话ID")
    message_id: str | None = Field(default=None, description="消息ID")
    user_message_id: str | None = Field(default=None, description="用户消息ID")
    assistant_created_at: str | None = Field(default=None, description="助手消息创建时间")
    timing: dict[str, int] | None = Field(default=None, description="耗时信息")
    request_id: str | None = Field(default=None, description="请求ID")
