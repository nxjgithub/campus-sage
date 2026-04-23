from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    """应用配置，统一从环境变量读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    qdrant_timeout_s: int = Field(default=30, description="Qdrant 请求超时秒数")
    qdrant_upsert_batch_size: int = Field(
        default=128, description="Qdrant 单次 upsert 批大小"
    )
    vector_backend: str = Field(default="qdrant", description="向量库后端（memory/qdrant）")
    vector_dim: int = Field(default=1024, description="向量维度")

    vllm_base_url: str = Field(default="http://127.0.0.1:8001/v1", description="vLLM 地址")
    vllm_model_name: str = Field(
        default="Qwen2.5-7B-Instruct", description="vLLM 模型名"
    )
    vllm_timeout_s: int = Field(default=60, description="vLLM 超时秒数")
    vllm_api_key: str | None = Field(default=None, description="vLLM API Key")
    vllm_enabled: bool = Field(default=False, description="是否启用 vLLM 生成")

    jwt_secret_key: str = Field(default="CHANGE_ME", description="JWT 密钥")
    jwt_algorithm: str = Field(default="HS256", description="JWT 算法")
    jwt_issuer: str = Field(default="csage", description="JWT 签发者")
    access_token_expire_minutes: int = Field(default=60, description="访问令牌过期分钟")
    refresh_token_expire_days: int = Field(default=7, description="刷新令牌过期天数")
    password_min_length: int = Field(default=8, description="密码最小长度")

    embedding_backend: Literal["http", "simple", "local"] = Field(
        default="http", description="Embedding 后端（http/simple/local）"
    )
    embedding_base_url: str = Field(
        default="http://127.0.0.1:8001/v1", description="Embedding 服务地址"
    )
    embedding_api_path: str = Field(
        default="/embeddings", description="Embedding 接口路径"
    )
    embedding_timeout_s: int = Field(default=60, description="Embedding 超时秒数")
    embedding_api_key: str | None = Field(default=None, description="Embedding API Key")
    embedding_model_name: str = Field(default="bge-m3", description="Embedding 模型名")
    embedding_batch_size: int = Field(default=32, description="Embedding 批大小")
    embedding_dimensions: int | None = Field(
        default=None, description="Embedding 输出维度（可选）"
    )
    local_embedding_model_name: str = Field(
        default="BAAI/bge-m3", description="本地 Embedding 模型名"
    )
    local_embedding_device: str = Field(
        default="cpu", description="本地 Embedding 运行设备"
    )
    local_embedding_normalize: bool = Field(
        default=True, description="本地 Embedding 是否归一化"
    )
    tei_model_id: str = Field(
        default="BAAI/bge-m3", description="TEI 模型 ID（供本地部署配置使用）"
    )
    tei_served_model_name: str = Field(
        default="bge-m3", description="TEI 对外服务模型名（供本地部署配置使用）"
    )
    tei_max_client_batch_size: int = Field(
        default=8, description="TEI 单次请求最大批量（供本地部署配置使用）"
    )
    tei_max_concurrent_requests: int = Field(
        default=64, description="TEI 最大并发请求数（供本地部署配置使用）"
    )
    hf_token: str | None = Field(
        default=None, description="Hugging Face 访问令牌（私有模型时使用）"
    )

    rerank_enabled: bool = Field(default=False, description="是否启用重排")
    rerank_model_name: str = Field(default="bge-reranker", description="重排模型名")

    rag_topk: int = Field(default=5, description="默认 TopK")
    rag_threshold: float = Field(default=0.25, description="默认拒答阈值")
    rag_max_context_tokens: int = Field(default=3000, description="上下文预算")
    rag_max_snippet_chars: int = Field(default=200, description="引用片段长度")
    rag_min_evidence_chunks: int = Field(default=1, description="最少证据数")
    rag_min_context_chars: int = Field(default=20, description="最少上下文字符数")
    rag_min_keyword_coverage: float = Field(default=0.3, description="关键词覆盖率阈值")
    rag_rerank_candidate_multiplier: int = Field(
        default=4,
        description="启用重排时的候选池放大倍数",
    )
    rag_rerank_candidate_cap: int = Field(
        default=40,
        description="启用重排时的最大候选池上限",
    )
    rag_stale_warning_days: int = Field(
        default=730,
        description="证据发布日期超过该天数时触发时效核验提示",
    )
    chunk_size: int = Field(default=500, description="分块大小（字符数）")
    chunk_overlap: int = Field(default=100, description="分块重叠（字符数）")

    storage_dir: str = Field(default="./data/storage", description="本地文件存储目录")
    upload_max_mb: int = Field(default=30, description="上传最大大小（MB）")
    upload_allowed_exts: str = Field(
        default="pdf,docx,html,htm,md,txt",
        description="允许的文件扩展名列表",
    )

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
    ingest_queue_failed_alert_threshold: int = Field(
        default=10, description="失败任务告警阈值"
    )
    ingest_queue_dead_max: int = Field(default=200, description="死信队列保留上限")

    debug_mode: bool = Field(default=False, description="调试模式")
    enable_swagger: bool = Field(default=True, description="是否启用 Swagger")

    @property
    def allowed_upload_extensions(self) -> tuple[str, ...]:
        """返回归一化后的允许上传后缀，供上传与诊断统一复用。"""

        configured = tuple(
            dict.fromkeys(
                ext.strip().lower()
                for ext in self.upload_allowed_exts.split(",")
                if ext.strip()
            )
        )
        # 兼容历史仅配置 pdf 的本地环境，自动放开首批稳定文本格式。
        if configured == ("pdf",):
            return ("pdf", "docx", "html", "htm", "md", "txt")
        return configured

    @property
    def database_backend(self) -> str:
        """提取数据库后端名称，便于诊断接口展示。"""

        parsed = urlparse(self.database_url)
        scheme = parsed.scheme or "unknown"
        if scheme.startswith("mysql"):
            return "mysql"
        return scheme

    @property
    def database_target(self) -> str:
        """返回脱敏后的数据库目标描述，便于运行时诊断。"""

        parsed = urlparse(self.database_url)
        if self.database_backend == "sqlite":
            target = parsed.path or parsed.netloc or self.database_url
            if target.startswith("/"):
                return target.lstrip("/")
            return target
        if self.database_backend == "mysql":
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 3306
            database_name = parsed.path.lstrip("/")
            if database_name:
                return f"{host}:{port}/{database_name}"
            return f"{host}:{port}"
        return parsed.path or parsed.netloc or self.database_url

    @property
    def jwt_secret_is_default(self) -> bool:
        """判断 JWT 密钥是否仍使用默认占位值。"""

        return self.jwt_secret_key == "CHANGE_ME"

    @property
    def jwt_secret_is_weak(self) -> bool:
        """判断 JWT 密钥长度是否低于推荐安全下限。"""

        return len(self.jwt_secret_key) < JWT_SECRET_MIN_LENGTH

    def runtime_errors(self) -> list[str]:
        """汇总会阻断服务启动的运行时配置错误。"""

        errors: list[str] = []
        if self.app_env.lower() != "prod":
            return errors
        if self.jwt_secret_is_default:
            errors.append("生产环境禁止使用默认 JWT_SECRET_KEY。")
        elif self.jwt_secret_is_weak:
            errors.append(
                f"生产环境要求 JWT_SECRET_KEY 至少 {JWT_SECRET_MIN_LENGTH} 个字符。"
            )
        return errors

    def runtime_warnings(self) -> list[str]:
        """汇总当前运行配置下需要额外关注的告警信息。"""

        warnings: list[str] = []
        if self.jwt_secret_is_default:
            warnings.append("JWT_SECRET_KEY 仍为默认值，部署前必须替换。")
        elif self.jwt_secret_is_weak:
            warnings.append(
                f"JWT_SECRET_KEY 长度过短，建议至少 {JWT_SECRET_MIN_LENGTH} 个字符。"
            )
        if not self.allowed_upload_extensions:
            warnings.append("UPLOAD_ALLOWED_EXTS 为空，上传接口将拒绝所有文件。")
        return warnings

    @field_validator("embedding_dimensions", mode="before")
    @classmethod
    def _normalize_embedding_dimensions(cls, value: object) -> object:
        """兼容空字符串配置，避免 Optional[int] 解析失败。"""

        if value == "":
            return None
        return value

    @field_validator(
        "qdrant_api_key",
        "vllm_api_key",
        "embedding_api_key",
        "hf_token",
        mode="before",
    )
    @classmethod
    def _normalize_optional_secret(cls, value: object) -> object:
        """将空字符串密钥统一视为 None，避免客户端携带空凭据。"""

        if value == "":
            return None
        return value


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取配置单例，避免重复解析环境变量。"""

    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """重置配置单例，供测试使用。"""

    global _settings
    _settings = None
