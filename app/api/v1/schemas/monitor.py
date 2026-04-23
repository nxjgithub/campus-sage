"""监控与运行时诊断 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class QueueStats(BaseModel):
    """队列统计信息。"""

    queued: int = Field(description="等待中的任务数")
    started: int = Field(description="执行中的任务数")
    deferred: int = Field(description="延迟队列任务数")
    finished: int = Field(description="已完成任务数")
    failed_registry: int = Field(description="失败注册表任务数")
    dead: int = Field(description="死信队列任务数")
    scheduled: int = Field(description="调度中的任务数")


class QueueStatsResponse(RequestIdMixin):
    """队列监控响应。"""

    stats: QueueStats = Field(description="当前队列统计")
    alerts: list[str] = Field(description="当前告警信息")


class QueueMoveDeadResponse(RequestIdMixin):
    """死信迁移响应。"""

    moved: int = Field(description="本次迁移任务数")


class RuntimeDatabaseInfo(BaseModel):
    """数据库运行时信息。"""

    backend: str = Field(description="数据库后端类型")
    target: str = Field(description="数据库目标位置")
    schema_version: int = Field(description="当前 schema 版本")


class RuntimeServicesInfo(BaseModel):
    """后端关键服务开关。"""

    vector_backend: str = Field(description="向量库后端")
    embedding_backend: str = Field(description="Embedding 后端")
    vllm_enabled: bool = Field(description="是否启用生成模型")
    ingest_queue_enabled: bool = Field(description="是否启用入库队列")


class RuntimeUploadInfo(BaseModel):
    """上传配置摘要。"""

    max_mb: int = Field(description="上传大小限制")
    allowed_exts: list[str] = Field(description="允许上传的后缀列表")


class RuntimeSecurityInfo(BaseModel):
    """安全相关配置摘要。"""

    jwt_default_secret: bool = Field(description="JWT 密钥是否仍为默认值")
    jwt_weak_secret: bool = Field(description="JWT 密钥长度是否低于推荐安全下限")


class RuntimeRagMetricsInfo(BaseModel):
    """RAG 运行时联调指标。"""

    sample_size: int = Field(description="统计样本数量（助手消息数）")
    refusal_count: int = Field(description="拒答消息数量")
    clarification_count: int = Field(description="澄清型拒答数量")
    freshness_warning_count: int = Field(description="时效提醒数量")
    citation_covered_count: int = Field(description="带引用的非拒答数量")
    refusal_rate: float = Field(description="拒答占比")
    clarification_rate: float = Field(description="澄清型拒答占比")
    freshness_warning_rate: float = Field(description="时效提醒占比")
    citation_coverage_rate: float = Field(description="非拒答消息的引用覆盖占比")


class RuntimeDiagnosticsResponse(RequestIdMixin):
    """运行时诊断响应。"""

    app_env: str = Field(description="当前运行环境")
    log_level: str = Field(description="日志级别")
    debug_mode: bool = Field(description="是否开启调试模式")
    enable_swagger: bool = Field(description="是否启用 Swagger")
    database: RuntimeDatabaseInfo = Field(description="数据库诊断信息")
    services: RuntimeServicesInfo = Field(description="关键服务配置")
    upload: RuntimeUploadInfo = Field(description="上传配置")
    security: RuntimeSecurityInfo = Field(description="安全配置")
    rag_metrics: RuntimeRagMetricsInfo = Field(description="RAG 运行时联调指标")
    warnings: list[str] = Field(description="运行时告警提示")
