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
    source_uri: str | None = Field(default=None, description="文档官方来源链接")
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


class StagedAssetResponse(BaseModel):
    """暂存图片资产响应。"""

    asset_id: str = Field(description="图片资产 ID")
    label: str = Field(description="图片展示编号")
    file_name: str = Field(description="原始图片文件名")
    media_type: str = Field(description="媒体类型")
    url: str = Field(description="图片访问地址")
    order_index: int = Field(description="图片在文档中的顺序")
    source: str = Field(description="资产来源")
    page_number: int | None = Field(default=None, description="PDF 图片所属页码")


class StagedAssetRefResponse(BaseModel):
    """暂存分块关联的图片资产引用。"""

    asset_id: str = Field(description="图片资产 ID")
    asset_label: str = Field(description="图片展示编号")
    asset_url: str = Field(description="图片访问地址")
    media_type: str | None = Field(default=None, description="媒体类型")
    file_name: str | None = Field(default=None, description="原始图片文件名")


class StagedPageResponse(BaseModel):
    """暂存解析页面响应。"""

    page_number: int | None = Field(default=None, description="页码")
    text: str = Field(description="解析文本")
    section_path: str | None = Field(default=None, description="章节路径")


class StagedChunkResponse(BaseModel):
    """暂存分块响应。"""

    chunk_id: str = Field(description="预览分块 ID")
    chunk_index: int = Field(description="分块序号")
    text: str = Field(description="分块文本")
    page_start: int | None = Field(default=None, description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    section_path: str | None = Field(default=None, description="章节路径")
    enabled: bool = Field(description="是否确认入库")
    source_kind: str = Field(description="分块来源类型")
    asset_id: str | None = Field(default=None, description="关联图片资产 ID")
    asset_label: str | None = Field(default=None, description="关联图片展示编号")
    asset_url: str | None = Field(default=None, description="关联图片访问地址")
    assets: list[StagedAssetRefResponse] | None = Field(
        default=None,
        description="关联图片资产列表",
    )


class StagedPreviewBlockResponse(BaseModel):
    """暂存预览结构块响应。"""

    block_type: Literal["heading", "paragraph", "table", "image"] = Field(
        description="结构块类型"
    )
    order_index: int = Field(description="结构块顺序")
    text: str | None = Field(default=None, description="文本内容")
    level: int | None = Field(default=None, description="标题级别")
    rows: list[list[str]] | None = Field(default=None, description="表格行")
    page_number: int | None = Field(default=None, description="页码")
    section_path: str | None = Field(default=None, description="章节路径")
    asset_id: str | None = Field(default=None, description="关联图片资产 ID")
    asset_label: str | None = Field(default=None, description="关联图片展示编号")
    asset_url: str | None = Field(default=None, description="关联图片访问地址")


class StagedDocumentResponse(RequestIdMixin):
    """暂存文档预览响应。"""

    staged_doc_id: str = Field(description="暂存文档 ID")
    kb_id: str = Field(description="知识库 ID")
    doc_name: str = Field(description="文档名称")
    doc_version: str | None = Field(default=None, description="文档版本")
    published_at: str | None = Field(default=None, description="发布日期")
    source_uri: str | None = Field(default=None, description="文档官方来源链接")
    filename: str = Field(description="原始文件名")
    extension: str = Field(description="扩展名")
    source_type: str = Field(description="来源类型")
    status: Literal["uploaded", "previewed"] = Field(description="暂存状态")
    assets: list[StagedAssetResponse] = Field(description="图片资产列表")
    pages: list[StagedPageResponse] = Field(description="解析页面列表")
    preview_blocks: list[StagedPreviewBlockResponse] = Field(description="版式预览结构块")
    chunks: list[StagedChunkResponse] = Field(description="预览分块列表")
    warnings: list[str] = Field(description="质量提醒")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class StagedChunkUpdateRequest(BaseModel):
    """暂存分块更新请求。"""

    enabled: bool | None = Field(default=None, description="是否入库")
    text: str | None = Field(default=None, description="分块文本")
