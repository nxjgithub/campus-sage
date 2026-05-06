# CONFIG.md — 配置项说明（环境变量）

本文档描述 CSage 的核心配置项。所有配置必须通过环境变量输入，并由 Settings 统一读取。
建议使用 `.env` 本地加载（提供 `.env.example`）。
补充：`.env` 允许同时存在 Docker Compose 辅助变量；`Settings` 会忽略未声明的辅助键，不会因此阻断应用启动。


## 1. 基础服务
- `APP_ENV`：运行环境（local/dev/prod），默认 local
- `APP_HOST`：默认 127.0.0.1
- `APP_PORT`：默认 8000
- `LOG_LEVEL`：INFO/DEBUG，默认 INFO


## 2. 数据库（MySQL 默认 / SQLite 兼容）
- `DATABASE_URL`
    - MySQL 示例：`mysql+pymysql://user:pass@127.0.0.1:3307/csage?charset=utf8mb4`
    - SQLite 兼容示例：`sqlite:///./data/csage.db`
- `CSAGE_DATABASE_URL_INTERNAL`
    - Docker Compose 内 `api/worker` 访问 MySQL 的内部连接串
    - 示例：`mysql+pymysql://csage:csage123@mysql:3306/csage?charset=utf8mb4`
- `CSAGE_MYSQL_DATABASE`：Docker Compose 中 MySQL 容器初始化数据库名，默认 `csage`
- `CSAGE_MYSQL_USER`：Docker Compose 中 MySQL 业务用户名，默认 `csage`
- `CSAGE_MYSQL_PASSWORD`：Docker Compose 中 MySQL 业务用户密码，默认 `csage123`
- `CSAGE_MYSQL_ROOT_PASSWORD`：Docker Compose 中 MySQL root 密码，默认 `csage_root`
- `CSAGE_MYSQL_HOST_PORT`：Docker Compose 暴露到宿主机的 MySQL 端口，默认 `3307`
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
- `VLLM_API_KEY`：OpenAI 兼容生成服务的 API Key，可为空
- `VLLM_ENABLED`：true/false，是否启用 vLLM 生成
- 流式问答说明：`VLLM_ENABLED=true` 时，`POST /api/v1/kb/{kb_id}/ask/stream` 会向 `/chat/completions` 发送 `stream=true`，并把上游 delta 透传为 SSE `token`；未启用 vLLM 时仅使用本地兜底答案切片。

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

### 4.2.1 Docker Compose / TEI 补充配置
- `EMBEDDING_BASE_URL_INTERNAL`：容器内 API / Worker 访问 Embedding 服务的地址，默认 `http://tei:80/v1`
- `EMBEDDING_API_PATH_INTERNAL`：容器内 Embedding 接口路径，默认 `/embeddings`
- `NO_PROXY_INTERNAL`：容器内跳过代理的主机列表，默认 `mysql,qdrant,tei,redis,minio,localhost,127.0.0.1`
- `TEI_MODEL_ID`：TEI 容器加载的模型 ID，默认 `BAAI/bge-m3`
- `TEI_SERVED_MODEL_NAME`：TEI 对外声明的模型名，默认 `bge-m3`
- `TEI_MAX_CLIENT_BATCH_SIZE`：TEI 单次请求最大批量，默认 `8`
- `TEI_MAX_CONCURRENT_REQUESTS`：TEI 最大并发请求数，默认 `64`
- `HF_TOKEN`：Hugging Face 访问令牌，拉取私有模型时使用，可为空

说明：
- `tei` 与 `minio-init` 服务会在 Compose 中显式清空 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式。`api/worker` 的 `NO_PROXY_INTERNAL` 必须包含 `minio`，否则启用 S3 图片存储时，容器内访问 MinIO 可能被错误转发到宿主机代理。
- 如果你的网络环境必须通过代理访问 Hugging Face，应先确保 Docker 容器内代理地址真实可达，再按需调整 `docker-compose.yml` 中 `tei.environment` 的代理变量。

### 4.3 Rerank（可选）
- `RERANK_ENABLED`：true/false
- `RERANK_MODEL_NAME`：如 `bge-reranker`（示例）

## 4.4 认证与安全
- `JWT_SECRET_KEY`：JWT 密钥（必须修改，且建议至少 32 个字符）
- `JWT_ALGORITHM`：默认 HS256
- `JWT_ISSUER`：默认 csage
- `ACCESS_TOKEN_EXPIRE_MINUTES`：访问令牌过期分钟
- `REFRESH_TOKEN_EXPIRE_DAYS`：刷新令牌过期天数
- `PASSWORD_MIN_LENGTH`：密码最小长度
说明：密码必须包含字母与数字，长度不足将返回 `PASSWORD_TOO_WEAK`。
补充：当 `APP_ENV=prod` 时，若 `JWT_SECRET_KEY` 仍为默认值或长度小于 32，服务将拒绝启动。


## 5. RAG 参数（可被 KB config 覆盖）
- `RAG_TOPK`：默认 5
- `RAG_THRESHOLD`：默认 0.25（分数阈值，低于则拒答）
- `RAG_MAX_CONTEXT_TOKENS`：默认 3000（上下文预算）
- `RAG_MAX_SNIPPET_CHARS`：默认 200（引用片段长度）
- `RAG_MIN_EVIDENCE_CHUNKS`：默认 1（最少有效证据数）
- `RAG_MIN_CONTEXT_CHARS`：默认 20（最少上下文字符数）
- `RAG_MIN_KEYWORD_COVERAGE`：默认 0.3（关键词覆盖率阈值）
- `RAG_RERANK_CANDIDATE_MULTIPLIER`：默认 4（启用重排时的候选池放大倍数）
- `RAG_RERANK_CANDIDATE_CAP`：默认 40（启用重排时的候选池上限）
- `RAG_STALE_WARNING_DAYS`：默认 730（时效问题下，证据发布日期超过该天数将追加“请核验最新公告”提示）
- `CHUNK_SIZE`：默认 500（分块目标大小，字符数；切片器会优先保留标题、段落和完整句子）
- `CHUNK_OVERLAP`：默认 100（分块重叠，字符数；实际重叠以完整语义单元为边界）

取值约束（同样适用于 KB config 覆盖值）：
- `topk`：`1~50`
- `threshold`：`0~1`
- `max_context_tokens`：`>=1`
- `min_evidence_chunks`：`>=1` 且不能大于 `topk`
- `min_context_chars`：`>=1`
- `min_keyword_coverage`：`0~1`

说明：
- 当 `rerank_enabled=true` 时，系统会先按 `RAG_RERANK_CANDIDATE_MULTIPLIER` 放大检索候选池，再执行启发式重排，最后截回最终 `topk`。
- 若本地 Embedding 质量一般，可适度提高该候选池；但过大也会带来额外延迟。
- 通知、公告、指南等 PDF 文档入库时，切片器会把首页标题和“一、二、三”等页内小节写入 `section_path`，并在长小节拆分时尽量保留小节标题作为每个 chunk 的语义锚点。
- 简单重排器会优先识别 `主要功能`、`参与方式`、`培训对象`、`开课时间`、`课程安排` 等通知类意图短语，避免仅含宽泛主题词的候选压过精确小节。


## 6. 上传与存储
- `STORAGE_DIR`：默认 `./data/storage`
- `ASSET_STORAGE_BACKEND`：图片资产存储后端，`local` 或 `s3`，默认 `local`
- `S3_ENDPOINT_URL`：S3/MinIO Endpoint，本地 MinIO 示例 `http://127.0.0.1:9002`
- `S3_ENDPOINT_URL_INTERNAL`：Docker Compose 内部 Endpoint，默认 `http://minio:9000`
- `S3_REGION`：S3 区域，默认 `us-east-1`
- `S3_BUCKET`：图片资产 Bucket，默认 `campus-sage-assets`
- `S3_PREFIX`：图片资产对象前缀，默认 `campus-sage`
- `S3_ACCESS_KEY_ID`：S3/MinIO Access Key
- `S3_SECRET_ACCESS_KEY`：S3/MinIO Secret Key
- `S3_USE_SSL`：是否使用 HTTPS，默认 `false`
- `S3_FORCE_PATH_STYLE`：是否使用 Path Style，MinIO 建议 `true`
- `UPLOAD_MAX_MB`：默认 30
- `UPLOAD_ALLOWED_EXTS`：默认 `pdf`（MVP 建议先只支持 pdf）

说明：`ASSET_STORAGE_BACKEND=s3` 时，DOCX 提取出的图片资产会写入 S3/MinIO；Docker Compose 默认启动本地 MinIO 与 bucket 初始化服务，避免容器内 S3 Endpoint 不可达；前端仍通过 `GET /api/v1/assets/{asset_id}` 鉴权访问，后端代理读取对象存储并返回图片流。`local` 模式保留本地文件读取，兼容既有演示数据。

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
- `INGEST_REQUIRE_HTTP_EMBEDDING`：是否要求入库必须使用 HTTP Embedding 服务，默认 false；Docker Compose 默认 true。启用后若 `EMBEDDING_BACKEND` 不是 `http`，入库任务会失败并提示重试。

## 8. 开关与调试
- `DEBUG_MODE`：true/false
- `ENABLE_SWAGGER`：true/false（prod 可关闭）

## 9. Schema 初始化与迁移说明（2026-04）
- SQLite：后端启动时会自动执行增量 schema 迁移，不再依赖 `init_database()` 内部的隐式 `ALTER TABLE` 补列。
- MySQL：后端启动时会自动执行空库初始化，直接建到当前最新 schema，并写入 `schema_migration`。
- MySQL 表和字段会写入中文 `COMMENT` 元数据，便于通过 DataGrip、Navicat 或 `information_schema` 理解字段含义。
- 迁移历史统一保存在 `schema_migration` 表，当前版本按代码内置迁移序列递增。
- 当前 schema 包含 `conversation_memory`，用于保存多轮检索改写所需的轻量摘要；该表内容不作为回答证据。
- 已存在的旧 SQLite 库会按版本顺序补齐缺失表、列与索引；全新 SQLite/MySQL 数据库会直接初始化到最新版本。
- 当前 MySQL 不支持“半迁移旧库”增量补丁；切换到 MySQL 时应使用全新的数据库实例。
- 开发与测试时如果怀疑 schema 未升级，可检查：
  - `SELECT version, name, applied_at FROM schema_migration ORDER BY version;`
  - SQLite：`PRAGMA table_info(document);`
  - MySQL：`SHOW COLUMNS FROM document;`

## 10. 配置归一化与诊断补充（2026-03）
- `UPLOAD_ALLOWED_EXTS` 会在运行时自动执行：
  - 去空白
  - 小写化
  - 去重并保留声明顺序
- 为兼容历史本地环境，若该配置仅为 `pdf`，系统会自动扩展为 `pdf,docx,html,htm,md,txt`。
- 管理员可通过 `GET /api/v1/monitor/runtime` 查看当前生效的关键配置摘要与告警信息。
- 运行时诊断会额外暴露 `security.jwt_default_secret` 与 `security.jwt_weak_secret`，用于区分“仍为默认值”和“长度过短”两类 JWT 风险。

## 上传类型补充（2026-03 第三轮）
- `UPLOAD_ALLOWED_EXTS` 默认值调整为 `pdf,docx,html,htm,md,txt`。
- 推荐首批启用文本可稳定提取的格式；`csv/xlsx/pptx/图片 OCR` 暂不纳入默认支持集。

## 11. 运行时观测（2026-03）
- `GET /api/v1/monitor/runtime` 会聚合最近助手消息形成 `rag_metrics`，用于观察拒答、澄清、时效提示和引用覆盖情况。
- 当前样本窗口由服务端固定控制（最近 200 条助手消息），无需额外环境变量配置。
