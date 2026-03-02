# CONFIG.md — 配置项说明（环境变量）

本文档描述 CSage 的核心配置项。所有配置必须通过环境变量输入，并由 Settings 统一读取。
建议使用 `.env` 本地加载（提供 `.env.example`）。


## 1. 基础服务
- `APP_ENV`：运行环境（local/dev/prod），默认 local
- `APP_HOST`：默认 127.0.0.1
- `APP_PORT`：默认 8000
- `LOG_LEVEL`：INFO/DEBUG，默认 INFO


## 2. 数据库（SQLite 起步 / MySQL 后期）
- `DATABASE_URL`
    - SQLite 示例：`sqlite:///./data/csage.db`
    - MySQL 示例：`mysql+pymysql://user:pass@127.0.0.1:3306/csage?charset=utf8mb4`
> 数据库字符集必须 utf8mb4（中文与表情符号更稳）。


## 3. 向量数据库（Qdrant）
- `QDRANT_URL`：如 `http://127.0.0.1:6333`
- `QDRANT_API_KEY`：可选
- `QDRANT_COLLECTION_PREFIX`：默认 `csage_`（用于区分环境）
- `QDRANT_TIMEOUT_S`：Qdrant 请求超时秒数，默认 `30`
- `QDRANT_UPSERT_BATCH_SIZE`：Qdrant 单次 upsert 批大小，默认 `128`
- `VECTOR_BACKEND`：向量库后端（memory/qdrant），默认 qdrant
- `VECTOR_DIM`：embedding 维度（与 embedding 模型一致）


## 4. 模型服务
### 4.1 vLLM（生成模型）
- `VLLM_BASE_URL`：如 `http://127.0.0.1:8001/v1`
- `VLLM_MODEL_NAME`：如 `Qwen2.5-7B-Instruct`（示例）
- `VLLM_TIMEOUT_S`：默认 60
- `VLLM_ENABLED`：true/false，是否启用 vLLM 生成
### 4.2 Embedding（向量模型）
- `EMBEDDING_BACKEND`：Embedding 后端（http/simple/local），默认 http
- `EMBEDDING_BASE_URL`：Embedding 服务地址（OpenAI 兼容），默认 `http://127.0.0.1:8001/v1`
- `EMBEDDING_API_PATH`：Embedding 接口路径，默认 `/embeddings`
- `EMBEDDING_TIMEOUT_S`：默认 60
- `EMBEDDING_API_KEY`：可选
- `EMBEDDING_MODEL_NAME`：如 `bge-m3`（示例）
- `EMBEDDING_BATCH_SIZE`：默认 32
- `EMBEDDING_DIMENSIONS`：可选，向 OpenAI 兼容服务传递输出维度（如 text-embedding-3）
- `LOCAL_EMBEDDING_MODEL_NAME`：本地 Embedding 模型名（方案 3 预留），默认 `BAAI/bge-m3`
- `LOCAL_EMBEDDING_DEVICE`：本地 Embedding 设备（方案 3 预留），默认 `cpu`
- `LOCAL_EMBEDDING_NORMALIZE`：本地 Embedding 是否归一化，默认 `true`

### 4.3 Rerank（可选）
- `RERANK_ENABLED`：true/false
- `RERANK_MODEL_NAME`：如 `bge-reranker`（示例）

## 4.4 认证与安全
- `JWT_SECRET_KEY`：JWT 密钥（必须修改）
- `JWT_ALGORITHM`：默认 HS256
- `JWT_ISSUER`：默认 csage
- `ACCESS_TOKEN_EXPIRE_MINUTES`：访问令牌过期分钟
- `REFRESH_TOKEN_EXPIRE_DAYS`：刷新令牌过期天数
- `PASSWORD_MIN_LENGTH`：密码最小长度
说明：密码必须包含字母与数字，长度不足将返回 `PASSWORD_TOO_WEAK`。


## 5. RAG 参数（可被 KB config 覆盖）
- `RAG_TOPK`：默认 5
- `RAG_THRESHOLD`：默认 0.25（分数阈值，低于则拒答）
- `RAG_MAX_CONTEXT_TOKENS`：默认 3000（上下文预算）
- `RAG_MAX_SNIPPET_CHARS`：默认 200（引用片段长度）
- `RAG_MIN_EVIDENCE_CHUNKS`：默认 1（最少有效证据数）
- `RAG_MIN_CONTEXT_CHARS`：默认 20（最少上下文字符数）
- `RAG_MIN_KEYWORD_COVERAGE`：默认 0.3（关键词覆盖率阈值）
- `CHUNK_SIZE`：默认 500（分块大小，字符数）
- `CHUNK_OVERLAP`：默认 100（分块重叠，字符数）

取值约束（同样适用于 KB config 覆盖值）：
- `topk`：`1~50`
- `threshold`：`0~1`
- `max_context_tokens`：`>=1`
- `min_evidence_chunks`：`>=1` 且不能大于 `topk`
- `min_context_chars`：`>=1`
- `min_keyword_coverage`：`0~1`


## 6. 上传与存储
- `STORAGE_DIR`：默认 `./data/storage`
- `UPLOAD_MAX_MB`：默认 30
- `UPLOAD_ALLOWED_EXTS`：默认 `pdf`（MVP 建议先只支持 pdf）

## 7. 任务队列（RQ + Redis）
- `REDIS_URL`：默认 `redis://127.0.0.1:6379/0`
- `INGEST_QUEUE_NAME`：默认 `ingest`
- `INGEST_QUEUE_ENABLED`：true/false，是否启用入库队列
 - `INGEST_QUEUE_TIMEOUT_S`：任务超时秒数，默认 600
 - `INGEST_QUEUE_RETRY_MAX`：重试次数，默认 2
 - `INGEST_QUEUE_RETRY_INTERVAL_S`：重试间隔秒数，默认 60
 - `INGEST_QUEUE_DEAD_NAME`：死信队列名，默认 `ingest_dead`
- `INGEST_QUEUE_RESULT_TTL_S`：结果保留秒数，默认 86400
- `INGEST_QUEUE_FAILURE_TTL_S`：失败保留秒数，默认 604800
- `INGEST_QUEUE_TTL_S`：排队任务保留秒数，默认 86400
- `INGEST_QUEUE_DASHBOARD_ENABLED`：是否启用队列面板，默认 false
- `INGEST_QUEUE_ALERT_THRESHOLD`：队列告警阈值，默认 200
- `INGEST_QUEUE_FAILED_ALERT_THRESHOLD`：失败任务告警阈值，默认 10
- `INGEST_QUEUE_DEAD_MAX`：死信队列保留上限，默认 200

## 8. 开关与调试
- `DEBUG_MODE`：true/false
- `ENABLE_SWAGGER`：true/false（prod 可关闭）
