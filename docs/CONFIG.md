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
- `VECTOR_BACKEND`：向量库后端（memory/qdrant），默认 memory
- `VECTOR_DIM`：embedding 维度（与 embedding 模型一致）


## 4. 模型服务
### 4.1 vLLM（生成模型）
- `VLLM_BASE_URL`：如 `http://127.0.0.1:8001/v1`
- `VLLM_MODEL_NAME`：如 `Qwen2.5-7B-Instruct`（示例）
- `VLLM_TIMEOUT_S`：默认 60
- `VLLM_ENABLED`：true/false，是否启用 vLLM 生成
### 4.2 Embedding（向量模型）
- `EMBEDDING_MODEL_NAME`：如 `bge-m3`（示例）
- `EMBEDDING_BATCH_SIZE`：默认 32

### 4.3 Rerank（可选）
- `RERANK_ENABLED`：true/false
- `RERANK_MODEL_NAME`：如 `bge-reranker`（示例）


## 5. RAG 参数（可被 KB config 覆盖）
- `RAG_TOPK`：默认 5
- `RAG_THRESHOLD`：默认 0.25（分数阈值，低于则拒答）
- `RAG_MAX_CONTEXT_TOKENS`：默认 3000（上下文预算）
- `RAG_MAX_SNIPPET_CHARS`：默认 200（引用片段长度）
- `RAG_MIN_EVIDENCE_CHUNKS`：默认 1（最少有效证据数）
- `CHUNK_SIZE`：默认 500（分块大小，字符数）
- `CHUNK_OVERLAP`：默认 100（分块重叠，字符数）


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
- `INGEST_QUEUE_DEAD_MAX`：死信队列保留上限，默认 200

## 8. 开关与调试
- `DEBUG_MODE`：true/false
- `ENABLE_SWAGGER`：true/false（prod 可关闭）
