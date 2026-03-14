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
    warnings: list[str] = Field(description="运行时告警提示")
