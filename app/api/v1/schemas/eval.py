"""评测相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class EvalItemCreate(BaseModel):
    """评测样本创建请求。"""

    question: str = Field(description="问题")
    gold_doc_id: str | None = Field(default=None, description="标准答案文档ID")
    gold_page_start: int | None = Field(default=None, description="标准页起始")
    gold_page_end: int | None = Field(default=None, description="标准页结束")
    tags: list[str] | None = Field(default=None, description="标签列表")


class EvalSetCreateRequest(BaseModel):
    """评测集创建请求。"""

    name: str = Field(description="评测集名称")
    description: str | None = Field(default=None, description="评测集描述")
    items: list[EvalItemCreate] = Field(description="评测样本列表")


class EvalSetResponse(RequestIdMixin):
    """评测集响应。"""

    eval_set_id: str = Field(description="评测集ID")
    name: str = Field(description="评测集名称")
    description: str | None = Field(default=None, description="评测集描述")
    item_count: int = Field(description="样本数量")
    created_at: str = Field(description="创建时间")


class EvalRunRequest(BaseModel):
    """评测运行请求。"""

    eval_set_id: str = Field(description="评测集ID")
    kb_id: str = Field(description="知识库ID")
    topk: int = Field(default=5, ge=1, le=50, description="检索TopK")
    threshold: float | None = Field(default=None, ge=0, le=1, description="命中阈值")
    rerank_enabled: bool | None = Field(default=None, description="是否启用重排")


class EvalMetrics(BaseModel):
    """评测指标。"""

    recall_at_k: float = Field(description="Recall@K")
    mrr: float = Field(description="MRR")
    avg_ms: int = Field(description="平均耗时（毫秒）")
    p95_ms: int = Field(description="P95耗时（毫秒）")
    samples: int = Field(description="样本数")


class EvalRunResponse(RequestIdMixin):
    """评测运行响应。"""

    run_id: str = Field(description="运行ID")
    eval_set_id: str = Field(description="评测集ID")
    kb_id: str = Field(description="知识库ID")
    topk: int = Field(description="检索TopK")
    threshold: float | None = Field(default=None, description="命中阈值")
    rerank_enabled: bool = Field(description="是否启用重排")
    metrics: EvalMetrics | None = Field(default=None, description="评测指标")
    created_at: str = Field(description="创建时间")
