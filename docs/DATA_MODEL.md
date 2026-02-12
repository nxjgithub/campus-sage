# DATA_MODEL.md — 数据模型设计（MVP 版）

本文档定义 CSage 的逻辑数据表（SQLite/MySQL 均适用）。
目标：支撑“可管理、可追溯、可评测”，同时避免过度设计。

> 注意：chunk 的全文与向量建议主要存向量库；数据库保留必要的审计与关联即可。


## 1. knowledge_base（知识库）
字段：
- `kb_id`（PK，string）
- `name`（string，唯一建议）
- `description`（text，nullable）
- `visibility`（string：public/internal/admin）
- `config_json`（text/json：topk/threshold/rerank/max_context_tokens 等）
- `created_at`（datetime）
- `updated_at`（datetime）

索引：
- unique(`name`)


## 2. document（文档）
字段：
- `doc_id`（PK，string）
- `kb_id`（FK -> knowledge_base.kb_id）
- `doc_name`（string）
- `doc_version`（string，nullable）
- `published_at`（date，nullable）
- `status`（string：pending/processing/indexed/failed/deleted）
- `error_message`（text，nullable）
- `file_path`（text：存储路径或对象存储 key）
- `file_sha256`（string，nullable，用于去重/审计）
- `chunk_count`（int，默认 0）
- `created_at`（datetime）
- `updated_at`（datetime）

索引：
- index(`kb_id`)
- index(`status`)
- index(`published_at`)


## 3. ingest_job（入库任务）
字段：
- `job_id`（PK，string）
- `kb_id`（FK）
- `doc_id`（FK）
- `status`（string：queued/running/succeeded/failed/canceled）
- `progress_json`（text/json：stage/pages_parsed/chunks_built/embeddings_done/vectors_upserted/stage_ms/parse_ms/chunk_ms/embed_ms/upsert_ms）
- `error_message`（text，nullable）
- `error_code`（string，nullable，用于机器可读原因码）
- `started_at`（datetime，nullable）
- `finished_at`（datetime，nullable）
- `created_at`（datetime）
- `updated_at`（datetime）

索引：
- index(`kb_id`)
- index(`doc_id`)
- index(`status`)


## 4. conversation（会话）
字段：
- `conversation_id`（PK，string）
- `kb_id`（FK）
- `user_id`（string，nullable：归属用户，匿名会话为空）
- `title`（string，nullable）
- `created_at`（datetime）
- `updated_at`（datetime）

索引：
- index(`kb_id`)
- index(`user_id`)
- index(`updated_at`)


## 5. message（消息）
字段：
- `message_id`（PK，string）
- `conversation_id`（FK）
- `role`（string：user/assistant）
- `content`（text）
- `refusal`（bool，assistant 才有意义）
- `refusal_reason`（string，nullable）
- `timing_json`（text/json：retrieve_ms/generate_ms/total_ms，可选）
- `created_at`（datetime）

索引：
- index(`conversation_id`)
- index(`created_at`)


## 6. citation（引用）
字段：
- `citation_row_id`（PK，自增或 UUID）
- `message_id`（FK -> message.message_id，指向 assistant 消息）
- `citation_id`（int：1..n，对应 [1][2]）
- `doc_id`（string）
- `doc_name`（string）
- `doc_version`（string，nullable）
- `published_at`（date，nullable）
- `page_start`（int，nullable）
- `page_end`（int，nullable）
- `section_path`（string，nullable）
- `chunk_id`（string）
- `snippet`（text）
- `score`（float，nullable）
- `created_at`（datetime）

索引：
- index(`message_id`)
- index(`doc_id`)


## 7. feedback（反馈）
字段：
- `feedback_id`（PK，string）
- `message_id`（FK）
- `rating`（string：up/down）
- `reasons_json`（text/json：数组，如 CITATION_IRRELEVANT/INCOMPLETE/HALLUCINATION）
- `comment`（text，nullable）
- `expected_hint`（text，nullable）
- `status`（string：received/triaged/resolved，可选）
- `created_at`（datetime）

索引：
- index(`message_id`)
- index(`rating`)
- index(`created_at`)


## 8. eval_set / eval_item（评测集）
### 8.1 eval_set
- `eval_set_id`（PK，string）
- `name`（string）
- `description`（text，nullable）
- `created_at`（datetime）

### 8.2 eval_item
- `eval_item_id`（PK，string）
- `eval_set_id`（FK）
- `question`（text）
- `gold_doc_id`（string，nullable）
- `gold_page_start`（int，nullable）
- `gold_page_end`（int，nullable）
- `tags_json`（text/json，nullable）
- `created_at`（datetime）

索引：
- index(`eval_set_id`)


## 9. eval_run / eval_result（评测运行与结果）
### 9.1 eval_run
- `run_id`（PK，string）
- `eval_set_id`（FK）
- `kb_id`（FK）
- `topk`（int）
- `threshold`（float，nullable）
- `rerank_enabled`（bool）
- `metrics_json`（text/json：recall_at_k/mrr/avg_ms/p95_ms）
- `created_at`（datetime）

### 9.2 eval_result（逐条结果，可选）
- `run_result_id`（PK，string）
- `run_id`（FK）
- `eval_item_id`（FK）
- `hit`（bool：gold 是否命中 TopK）
- `rank`（int，nullable：gold 在结果中的名次）
- `retrieve_ms`（int，nullable）
- `notes`（text，nullable）
- `created_at`（datetime）

索引：
- index(`run_id`)
- index(`eval_item_id`)


## 10. user / role / user_role（用户与角色）
### 10.1 user
- `user_id`（PK，string）
- `email`（string，唯一）
- `password_hash`（string）
- `status`（string：active/disabled/deleted）
- `created_at`（datetime）
- `updated_at`（datetime）
- `last_login_at`（datetime，nullable）

索引：
- unique(`email`)
- index(`status`)

### 10.2 role
- `role_id`（PK，string）
- `name`（string，唯一）
- `permissions_json`（text/json：权限列表）
- `created_at`（datetime）

### 10.3 user_role
- `user_id`（FK -> user.user_id）
- `role_id`（FK -> role.role_id）
- `created_at`（datetime）

索引：
- PK(`user_id`, `role_id`)


## 11. kb_access（知识库访问控制）
字段：
- `user_id`（FK -> user.user_id）
- `kb_id`（FK -> knowledge_base.kb_id）
- `access_level`（string：read/write/admin）
- `created_at`（datetime）
- `updated_at`（datetime）

索引：
- PK(`user_id`, `kb_id`)
- index(`user_id`)
- index(`kb_id`)


## 12. refresh_token（刷新令牌）
字段：
- `token_id`（PK，string）
- `user_id`（FK -> user.user_id）
- `token_hash`（string，唯一）
- `expires_at`（datetime）
- `revoked`（bool）
- `created_at`（datetime）
- `revoked_at`（datetime，nullable）

索引：
- unique(`token_hash`)
- index(`user_id`)
