"""知识库相关 Schema。"""

from __future__ import annotations

from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

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
    web_enabled: bool = Field(default=False, description="是否启用受控联网检索")
    allowed_web_prefixes: list[str] = Field(
        default_factory=list,
        description="允许联网访问的 URL 前缀",
    )
    web_seed_urls: list[str] = Field(
        default_factory=list,
        description="联网检索入口页 URL",
    )
    web_search_topk: int | None = Field(
        default=None, ge=1, le=10, description="联网证据最大返回条数"
    )

    @field_validator("allowed_web_prefixes", "web_seed_urls")
    @classmethod
    def validate_web_urls(cls, value: list[str]) -> list[str]:
        """校验联网检索 URL 配置只允许 http/https。"""

        for item in value:
            if not _is_allowed_web_url(item):
                raise ValueError("联网检索 URL 必须使用 http/https")
        return value

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
    web_enabled: bool | None = Field(default=None, description="是否启用受控联网检索")
    allowed_web_prefixes: list[str] | None = Field(
        default=None,
        description="允许联网访问的 URL 前缀",
    )
    web_seed_urls: list[str] | None = Field(
        default=None,
        description="联网检索入口页 URL",
    )
    web_search_topk: int | None = Field(
        default=None, ge=1, le=10, description="联网证据最大返回条数"
    )

    @field_validator("allowed_web_prefixes", "web_seed_urls")
    @classmethod
    def validate_partial_web_urls(cls, value: list[str] | None) -> list[str] | None:
        """校验局部更新中的联网检索 URL 配置。"""

        if value is None:
            return None
        for item in value:
            if not _is_allowed_web_url(item):
                raise ValueError("联网检索 URL 必须使用 http/https")
        return value

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
    description: str | None = Field(default=None, description="知识库说明")
    visibility: Literal["public", "internal", "admin"] = Field(description="可见性")
    config: KnowledgeBaseConfig = Field(description="RAG 参数配置")
    updated_at: str = Field(description="更新时间")


class KnowledgeBaseListResponse(RequestIdMixin):
    """知识库列表响应。"""

    items: list[KnowledgeBaseListItem] = Field(description="知识库列表")


def _is_allowed_web_url(value: str) -> bool:
    """校验联网检索 URL 不指向本机或内网地址。"""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().strip("[]")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        address = ip_address(hostname)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local)
