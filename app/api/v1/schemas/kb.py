"""知识库相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.api.v1.schemas.common import RequestIdMixin


class KnowledgeBaseConfig(BaseModel):
    """知识库配置。"""

    topk: int = Field(ge=1, le=50, description="TopK")
    threshold: float = Field(ge=0, le=1, description="拒答阈值")
    rerank_enabled: bool = Field(description="是否启用重排")
    max_context_tokens: int = Field(ge=1, description="上下文预算")
    min_evidence_chunks: int | None = Field(
        default=None, ge=1, description="最小证据数"
    )
    min_context_chars: int | None = Field(
        default=None, ge=1, description="最小上下文字符数"
    )
    min_keyword_coverage: float | None = Field(
        default=None, ge=0, le=1, description="关键词覆盖率阈值"
    )

    @model_validator(mode="after")
    def validate_evidence_consistency(self) -> "KnowledgeBaseConfig":
        """校验最小证据数量与 topk 的一致性。"""

        if (
            self.min_evidence_chunks is not None
            and self.min_evidence_chunks > self.topk
        ):
            raise ValueError("min_evidence_chunks 不能大于 topk")
        return self


class KnowledgeBaseConfigUpdate(BaseModel):
    """知识库配置局部更新。"""

    topk: int | None = Field(default=None, ge=1, le=50, description="TopK")
    threshold: float | None = Field(default=None, ge=0, le=1, description="拒答阈值")
    rerank_enabled: bool | None = Field(default=None, description="是否启用重排")
    max_context_tokens: int | None = Field(default=None, ge=1, description="上下文预算")
    min_evidence_chunks: int | None = Field(
        default=None, ge=1, description="最小证据数"
    )
    min_context_chars: int | None = Field(
        default=None, ge=1, description="最小上下文字符数"
    )
    min_keyword_coverage: float | None = Field(
        default=None, ge=0, le=1, description="关键词覆盖率阈值"
    )

    @model_validator(mode="after")
    def validate_partial_evidence_consistency(self) -> "KnowledgeBaseConfigUpdate":
        """在同一请求同时提供 topk 与最小证据时做即时校验。"""

        if (
            self.topk is not None
            and self.min_evidence_chunks is not None
            and self.min_evidence_chunks > self.topk
        ):
            raise ValueError("min_evidence_chunks 不能大于 topk")
        return self


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
    config: KnowledgeBaseConfigUpdate | None = Field(
        default=None, description="RAG 参数配置（支持局部更新）"
    )


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
