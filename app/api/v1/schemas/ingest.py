"""入库任务 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class IngestProgress(BaseModel):
    """入库进度。"""

    stage: Literal[
        "running",
        "parse",
        "chunk",
        "embed",
        "upsert",
        "done",
        "canceled",
        "failed",
    ] = Field(description="当前阶段")
    pages_parsed: int = Field(description="已解析页数")
    chunks_built: int = Field(description="已构建分块数量")
    embeddings_done: int = Field(description="已生成向量数量")
    vectors_upserted: int = Field(description="已写入向量数量")
    stage_ms: int = Field(description="当前阶段耗时（毫秒）")
    parse_ms: int = Field(description="解析阶段耗时（毫秒）")
    chunk_ms: int = Field(description="切分阶段耗时（毫秒）")
    embed_ms: int = Field(description="向量化阶段耗时（毫秒）")
    upsert_ms: int = Field(description="写入阶段耗时（毫秒）")


class IngestJobResponse(BaseModel):
    """入库任务信息。"""

    job_id: str = Field(description="任务ID")
    kb_id: str = Field(description="知识库ID")
    doc_id: str = Field(description="文档ID")
    status: Literal["queued", "running", "succeeded", "failed", "canceled"] = Field(
        description="任务状态"
    )
    progress: IngestProgress | None = Field(default=None, description="进度信息")
    error_message: str | None = Field(default=None, description="错误信息")
    error_code: str | None = Field(default=None, description="错误原因码")
    started_at: str | None = Field(default=None, description="开始时间")
    finished_at: str | None = Field(default=None, description="结束时间")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class IngestJobDetailResponse(IngestJobResponse, RequestIdMixin):
    """入库任务详情响应。"""
