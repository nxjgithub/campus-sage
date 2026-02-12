"""知识库相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class KnowledgeBaseConfig(BaseModel):
    """知识库配置。"""

    topk: int = Field(description="TopK")
    threshold: float = Field(description="拒答阈值")
    rerank_enabled: bool = Field(description="是否启用重排")
    max_context_tokens: int = Field(description="上下文预算")
    min_evidence_chunks: int | None = Field(default=None, description="最小证据数")
    min_context_chars: int | None = Field(default=None, description="最小上下文字符数")
    min_keyword_coverage: float | None = Field(default=None, description="关键词覆盖率阈值")


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求。"""

    name: str = Field(description="知识库名称")
    description: str | None = Field(default=None, description="知识库说明")
    visibility: Literal["public", "internal", "admin"] = Field(
        default="internal", description="可见性"
    )
    config: KnowledgeBaseConfig | None = Field(default=None, description="RAG 参数配置")


class KnowledgeBaseUpdateRequest(BaseModel):
    """更新知识库请求。"""

    description: str | None = Field(default=None, description="知识库说明")
    visibility: Literal["public", "internal", "admin"] | None = Field(
        default=None, description="可见性"
    )
    config: KnowledgeBaseConfig | None = Field(default=None, description="RAG 参数配置")


class KnowledgeBaseResponse(RequestIdMixin):
    """知识库详情响应。"""

    kb_id: str = Field(description="知识库ID")
    name: str = Field(description="知识库名称")
    description: str | None = Field(default=None, description="知识库说明")
    visibility: Literal["public", "internal", "admin"] = Field(description="可见性")
    config: KnowledgeBaseConfig = Field(description="RAG 参数配置")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class KnowledgeBaseListItem(BaseModel):
    """知识库列表项。"""

    kb_id: str = Field(description="知识库ID")
    name: str = Field(description="知识库名称")
    visibility: Literal["public", "internal", "admin"] = Field(description="可见性")
    updated_at: str = Field(description="更新时间")


class KnowledgeBaseListResponse(RequestIdMixin):
    """知识库列表响应。"""

    items: list[KnowledgeBaseListItem] = Field(description="知识库列表")
