from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置（统一从环境变量读取）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="local", description="运行环境（local/dev/prod）")
    app_host: str = Field(default="127.0.0.1", description="服务监听地址")
    app_port: int = Field(default=8000, description="服务监听端口")
    log_level: str = Field(default="INFO", description="日志级别")

    database_url: str = Field(
        default="sqlite:///./data/csage.db", description="数据库连接字符串"
    )

    qdrant_url: str = Field(default="http://127.0.0.1:6333", description="Qdrant 地址")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant API Key")
    qdrant_collection_prefix: str = Field(
        default="csage_", description="向量库集合前缀"
    )
    vector_backend: str = Field(default="memory", description="向量库后端（memory/qdrant）")
    vector_dim: int = Field(default=1024, description="向量维度")

    vllm_base_url: str = Field(default="http://127.0.0.1:8001/v1", description="vLLM 地址")
    vllm_model_name: str = Field(default="Qwen2.5-7B-Instruct", description="vLLM 模型名")
    vllm_timeout_s: int = Field(default=60, description="vLLM 超时秒数")
    vllm_enabled: bool = Field(default=False, description="是否启用 vLLM 生成")

    embedding_model_name: str = Field(default="bge-m3", description="Embedding 模型名")
    embedding_batch_size: int = Field(default=32, description="Embedding 批大小")

    rerank_enabled: bool = Field(default=False, description="是否启用重排")
    rerank_model_name: str = Field(default="bge-reranker", description="重排模型名")

    rag_topk: int = Field(default=5, description="默认 TopK")
    rag_threshold: float = Field(default=0.25, description="默认拒答阈值")
    rag_max_context_tokens: int = Field(default=3000, description="上下文预算")
    rag_max_snippet_chars: int = Field(default=200, description="引用片段长度")
    rag_min_evidence_chunks: int = Field(default=1, description="最少证据数")
    chunk_size: int = Field(default=500, description="分块大小（字符数）")
    chunk_overlap: int = Field(default=100, description="分块重叠（字符数）")

    storage_dir: str = Field(default="./data/storage", description="本地文件存储目录")
    upload_max_mb: int = Field(default=30, description="上传最大大小（MB）")
    upload_allowed_exts: str = Field(default="pdf", description="允许的文件扩展名列表")

    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0", description="Redis 连接地址"
    )
    ingest_queue_name: str = Field(default="ingest", description="入库队列名称")
    ingest_queue_enabled: bool = Field(default=False, description="是否启用入库队列")
    ingest_queue_timeout_s: int = Field(default=600, description="入库任务超时（秒）")
    ingest_queue_retry_max: int = Field(default=2, description="入库任务重试次数")
    ingest_queue_retry_interval_s: int = Field(
        default=60, description="入库任务重试间隔（秒）"
    )
    ingest_queue_dead_name: str = Field(default="ingest_dead", description="入库死信队列")
    ingest_queue_result_ttl_s: int = Field(default=86400, description="队列结果保留秒数")
    ingest_queue_failure_ttl_s: int = Field(default=604800, description="失败记录保留秒数")
    ingest_queue_ttl_s: int = Field(default=86400, description="排队任务保留秒数")
    ingest_queue_dashboard_enabled: bool = Field(
        default=False, description="是否启用 RQ Dashboard"
    )
    ingest_queue_alert_threshold: int = Field(default=200, description="队列告警阈值")
    ingest_queue_dead_max: int = Field(default=200, description="死信队列保留上限")

    debug_mode: bool = Field(default=False, description="调试模式")
    enable_swagger: bool = Field(default=True, description="是否启用 Swagger")


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取配置单例，避免重复解析环境变量。"""

    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
