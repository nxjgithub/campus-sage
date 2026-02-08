"""文档相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin
from app.api.v1.schemas.ingest import IngestJobResponse


class DocumentResponse(BaseModel):
    """文档基础信息。"""

    doc_id: str = Field(description="文档ID")
    kb_id: str = Field(description="知识库ID")
    doc_name: str = Field(description="文档名称")
    doc_version: str | None = Field(default=None, description="文档版本")
    published_at: str | None = Field(default=None, description="发布日期")
    status: Literal["pending", "processing", "indexed", "failed", "deleted"] = Field(
        description="文档状态"
    )
    error_message: str | None = Field(default=None, description="错误信息")
    chunk_count: int = Field(description="分块数量")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class DocumentDetailResponse(DocumentResponse, RequestIdMixin):
    """文档详情响应。"""


class DocumentListResponse(RequestIdMixin):
    """文档列表响应。"""

    items: list[DocumentResponse] = Field(description="文档列表")


class DocumentUploadResponse(RequestIdMixin):
    """上传文档响应。"""

    doc: DocumentResponse = Field(description="文档信息")
    job: IngestJobResponse = Field(description="任务信息")
