# API_SPEC.md — CampusSage API 规范（MVP → 可扩展）

本文档定义 CampusSage（CSage）后端 API 规范（FastAPI）。目标：接口形状稳定、错误格式统一、支持 RAG 证据链与可观测性。

通用约定：
`API 前缀`：`/api/v1`  
`响应格式`：JSON  
`编码`：UTF-8  
`request_id`：建议每个响应返回 `request_id`，并在 Header 返回 `X-Request-ID`


## 0. 统一响应与错误格式
### 0.1 成功响应
成功响应返回业务对象，**不强制**包一层 `data`，但建议统一包含：
`request_id: str`

### 0.2 失败响应（强制）
失败响应必须统一为：
```json
{
  "error": {
    "code": "RAG_NO_EVIDENCE",
    "message": "当前知识库中未找到足够证据，无法给出可靠答案。",
    "detail": {"kb_id": "kb_xxx", "topk": 5}
  },
  "request_id": "req_xxx"
}
```
字段说明：
`code`：错误码（枚举化，参见 `docs/CONVENTIONS.md`）  
`message`：中文错误信息  
`detail`：可选，结构化上下文信息


## 1. 数据模型（概览）
### 1.1 KnowledgeBase
`kb_id: str`  
`name: str`  
`description: str | null`  
`visibility: str`（"public" | "internal" | "admin"）  
`config: object`（RAG 参数，如 topk/threshold/rerank_enabled/max_context_tokens）  
`created_at: str`  
`updated_at: str`

### 1.2 Document
`doc_id: str`  
`kb_id: str`  
`doc_name: str`  
`doc_version: str | null`  
`published_at: str | null`  
`status: str`（"pending" | "processing" | "indexed" | "failed" | "deleted"）  
`error_message: str | null`  
`chunk_count: int`  
`created_at: str`  
`updated_at: str`

### 1.3 IngestJob
`job_id: str`  
`kb_id: str`  
`doc_id: str`  
`status: str`（"queued" | "running" | "succeeded" | "failed" | "canceled"）  
`progress: object | null`（可选：stage/pages_parsed/chunks_built/embeddings_done/vectors_upserted/stage_ms/parse_ms/chunk_ms/embed_ms/upsert_ms）  
`error_message: str | null`  
`error_code: str | null`  
`started_at: str | null`  
`finished_at: str | null`  
`created_at: str`  
`updated_at: str`

### 1.4 Citation（与 `docs/RAG_CONTRACT.md` 对齐）
`citation_id: int`  
`doc_id: str`  
`doc_name: str`  
`doc_version: str | null`  
`published_at: str | null`  
`page_start: int | null`  
`page_end: int | null`  
`section_path: str | null`  
`chunk_id: str`  
`snippet: str`  
`score: float | null`

> 说明：`score` 用于调试与可解释性，默认可为 null；当请求 `debug=true` 时建议返回真实分数。

### 1.5 AskResponse
`answer: str`  
`refusal: bool`  
`refusal_reason: str | null`  
`suggestions: List[str]`  
`citations: List[Citation]`  
`conversation_id: str | null`  
`message_id: str | null`  
`timing: object | null`（retrieve_ms/rerank_ms/context_ms/generate_ms/total_ms）  
`request_id: str | null`


## 2. Knowledge Base 接口
### 2.1 创建知识库
`POST /api/v1/kb`

请求 JSON：
```json
{
  "name": "教务知识库",
  "description": "选课、考试、补考等制度",
  "visibility": "internal",
  "config": {
    "topk": 5,
    "threshold": 0.25,
    "rerank_enabled": false,
    "max_context_tokens": 3000
  }
}
```

响应示例：
```json
{
  "kb_id": "kb_123",
  "name": "教务知识库",
  "description": "选课、考试、补考等制度",
  "visibility": "internal",
  "config": {"topk": 5, "threshold": 0.25, "rerank_enabled": false, "max_context_tokens": 3000},
  "created_at": "2026-02-07T10:00:00Z",
  "updated_at": "2026-02-07T10:00:00Z",
  "request_id": "req_xxx"
}
```

### 2.2 获取知识库列表
`GET /api/v1/kb`

响应示例：
```json
{
  "items": [
    {"kb_id": "kb_123", "name": "教务知识库", "visibility": "internal", "updated_at": "2026-02-07T10:00:00Z"}
  ],
  "request_id": "req_xxx"
}
```

### 2.3 获取知识库详情
`GET /api/v1/kb/{kb_id}`

### 2.4 更新知识库（含 RAG 参数）
`PATCH /api/v1/kb/{kb_id}`

请求示例：
```json
{
  "description": "更新说明",
  "config": {"topk": 8, "threshold": 0.22, "rerank_enabled": true}
}
```

### 2.5 删除知识库
`DELETE /api/v1/kb/{kb_id}`

说明：建议先做逻辑删除，避免误删。
同时删除该知识库关联的文档与入库任务，并清理向量库。


## 3. Document 与入库接口（Ingest）
### 3.1 上传文档并触发入库（推荐异步）
`POST /api/v1/kb/{kb_id}/documents`

Content-Type：`multipart/form-data`

表单字段：
`file`：上传文件（建议先支持 PDF）  
`doc_name`：可选，不传则使用文件名  
`doc_version`：可选  
`published_at`：可选，格式 `YYYY-MM-DD`

响应示例：
```json
{
  "doc": {
    "doc_id": "doc_123",
    "kb_id": "kb_123",
    "doc_name": "教务管理规定.pdf",
    "doc_version": "2025-09",
    "published_at": "2025-09-01",
    "status": "processing",
    "chunk_count": 0,
    "error_message": null
  },
  "job": {"job_id": "job_456", "status": "queued"},
  "request_id": "req_xxx"
}
```
说明：入库默认后台执行，返回时 `job.status=queued`，可通过 `GET /api/v1/ingest/jobs/{job_id}` 轮询进度。

### 3.2 获取文档列表
`GET /api/v1/kb/{kb_id}/documents`

### 3.3 获取文档详情
`GET /api/v1/documents/{doc_id}`

### 3.4 删除文档（联动删除向量）
`DELETE /api/v1/documents/{doc_id}`

说明：必须删除向量库中 `doc_id` 对应的点（按 payload 过滤删除）。
同时删除该文档关联的入库任务（ingest_job）。

### 3.5 重新入库 / 重建索引
`POST /api/v1/documents/{doc_id}/reindex`

### 3.6 获取入库任务状态
`GET /api/v1/ingest/jobs/{job_id}`

响应示例：
```json
{
  "job_id": "job_456",
  "kb_id": "kb_123",
  "doc_id": "doc_123",
  "status": "running",
  "progress": {
    "stage": "chunk",
    "pages_parsed": 3,
    "chunks_built": 42,
    "embeddings_done": 42,
    "vectors_upserted": 42,
    "stage_ms": 18,
    "parse_ms": 12,
    "chunk_ms": 6,
    "embed_ms": 0,
    "upsert_ms": 0
  },
  "error_message": null,
  "error_code": null,
  "started_at": "2026-02-07T10:01:00Z",
  "finished_at": null,
  "created_at": "2026-02-07T10:00:00Z",
  "updated_at": "2026-02-07T10:05:00Z",
  "request_id": "req_xxx"
}
```

### 3.7 取消入库任务
`POST /api/v1/ingest/jobs/{job_id}/cancel`

说明：
- 若任务处于 `queued/running`，将标记为 `canceled`
- 若任务已结束（`succeeded/failed`），取消为幂等（返回原状态）

响应示例：
```json
{
  "job_id": "job_456",
  "kb_id": "kb_123",
  "doc_id": "doc_123",
  "status": "canceled",
  "progress": {
    "stage": "canceled",
    "pages_parsed": 0,
    "chunks_built": 0,
    "embeddings_done": 0,
    "vectors_upserted": 0,
    "stage_ms": 0,
    "parse_ms": 0,
    "chunk_ms": 0,
    "embed_ms": 0,
    "upsert_ms": 0
  },
  "error_message": "入库已取消",
  "error_code": "INGEST_CANCELED",
  "started_at": "2026-02-07T10:01:00Z",
  "finished_at": "2026-02-07T10:02:00Z",
  "created_at": "2026-02-07T10:00:00Z",
  "updated_at": "2026-02-07T10:02:00Z",
  "request_id": "req_xxx"
}
```

### 3.8 重试入库任务
`POST /api/v1/ingest/jobs/{job_id}/retry`

说明：
- 仅 `failed/canceled` 任务允许重试
- 重试会创建新任务并返回新 `job_id`
- 不可重试时返回 `409 + INGEST_JOB_NOT_RETRYABLE`

响应示例：
```json
{
  "job_id": "job_789",
  "kb_id": "kb_123",
  "doc_id": "doc_123",
  "status": "queued",
  "progress": null,
  "error_message": null,
  "error_code": null,
  "started_at": null,
  "finished_at": null,
  "created_at": "2026-02-07T10:03:00Z",
  "updated_at": "2026-02-07T10:03:00Z",
  "request_id": "req_xxx"
}
```


## 4. 问答接口（RAG）
### 4.1 发起问答
`POST /api/v1/kb/{kb_id}/ask`

最小请求：
```json
{"question": "补考申请需要满足什么条件？"}
```

带参数覆盖：
```json
{
  "question": "补考申请需要满足什么条件？",
  "conversation_id": "conv_001",
  "topk": 8,
  "threshold": 0.22,
  "rerank_enabled": true,
  "filters": {"doc_ids": ["doc_123"], "published_after": "2024-01-01"},
  "debug": false
}
```

正常回答示例：
```json
{
  "answer": "根据教务管理规定，补考通常适用于……[1][2]",
  "refusal": false,
  "refusal_reason": null,
  "suggestions": [],
  "citations": [
    {
      "citation_id": 1,
      "doc_id": "doc_123",
      "doc_name": "教务管理规定.pdf",
      "doc_version": "2025-09",
      "published_at": "2025-09-01",
      "page_start": 12,
      "page_end": 12,
      "section_path": "考试管理/补考规定",
      "chunk_id": "chunk_a",
      "snippet": "……补考申请条件包括……",
      "score": 0.78
    }
  ],
  "conversation_id": "conv_001",
  "message_id": "msg_789",
  "timing": {"retrieve_ms": 45, "rerank_ms": 0, "context_ms": 12, "generate_ms": 380, "total_ms": 450},
  "request_id": "req_xxx"
}
```

拒答示例：
```json
{
  "answer": "当前知识库中未找到足够证据，无法给出可靠答案。建议到教务处官网或咨询学院办公室确认。",
  "refusal": true,
  "refusal_reason": "NO_EVIDENCE",
  "suggestions": ["建议关键词：补考 申请 条件", "建议到：教务处官网 考试管理栏目"],
  "citations": [],
  "conversation_id": "conv_001",
  "message_id": "msg_790",
  "timing": {"retrieve_ms": 35, "rerank_ms": 0, "context_ms": 8, "generate_ms": 120, "total_ms": 180},
  "request_id": "req_xxx"
}
```
说明：`debug=true` 时会返回 `citations.score`，否则可为 `null`。

约束：`citations` 与 `refusal` 规则必须符合 `docs/RAG_CONTRACT.md`。


## 5. 会话与历史（MVP 可简化）
### 5.1 获取会话列表
`GET /api/v1/conversations`

可选查询参数：`kb_id`、`limit`、`offset`

### 5.2 获取会话详情（含消息与引用）
`GET /api/v1/conversations/{conversation_id}`

响应示例：
```json
{
  "conversation_id": "conv_001",
  "kb_id": "kb_123",
  "messages": [
    {
      "message_id": "msg_789",
      "role": "user",
      "content": "补考申请需要满足什么条件？",
      "created_at": "2026-02-07T10:10:00Z"
    },
    {
      "message_id": "msg_790",
      "role": "assistant",
      "content": "根据教务管理规定……[1]",
      "citations": [],
      "refusal": false,
      "refusal_reason": null,
      "timing": {"retrieve_ms": 45, "rerank_ms": 0, "context_ms": 12, "generate_ms": 380, "total_ms": 450},
      "created_at": "2026-02-07T10:10:02Z"
    }
  ],
  "request_id": "req_xxx"
}
```
说明：`assistant` 消息包含 `citations/refusal/refusal_reason/timing` 字段，`user` 消息不包含这些字段。


## 6. 反馈（Feedback）
### 6.1 提交对某条消息的反馈
`POST /api/v1/messages/{message_id}/feedback`

请求示例：
```json
{
  "rating": "down",
  "reasons": ["CITATION_IRRELEVANT", "INCOMPLETE"],
  "comment": "引用内容不对应补考条件。",
  "expected_hint": "应引用补考申请条件那一段。"
}
```

响应示例：
```json
{
  "feedback_id": "fb_001",
  "message_id": "msg_790",
  "status": "received",
  "request_id": "req_xxx"
}
```


## 7. 评测（Eval，可选但建议）
说明：MVP 可先用脚本完成评测。如需 API，可按以下接口扩展。

### 7.1 创建评测集
`POST /api/v1/eval/sets`

请求示例：
```json
{
  "name": "教务评测集_v1",
  "items": [
    {"question": "缓考申请流程是什么？", "gold_doc_id": "doc_123", "gold_page_start": 5, "gold_page_end": 6}
  ]
}
```

### 7.2 运行评测
`POST /api/v1/eval/runs`

请求示例：
```json
{"eval_set_id": "es_001", "kb_id": "kb_123", "topk": 5}
```

### 7.3 获取评测结果
`GET /api/v1/eval/runs/{run_id}`

响应建议包含：`recall_at_k`、`mrr`、`avg_ms`、`p95_ms`


## 8. 监控（Queue Monitor，可选）
### 8.1 获取队列统计
`GET /api/v1/monitor/queues`

响应示例：
```json
{
  "stats": {
    "queued": 0,
    "started": 0,
    "deferred": 0,
    "finished": 0,
    "failed_registry": 0,
    "dead": 0,
    "scheduled": 0
  },
  "alerts": [],
  "request_id": "req_xxx"
}
```

### 8.2 将失败任务转入死信队列
`POST /api/v1/monitor/queues/ingest/move-dead`

响应示例：
```json
{
  "moved": 3,
  "request_id": "req_xxx"
}
```


## 9. 状态码建议映射
`400`：入参校验失败（VALIDATION_*）  
`401/403`：鉴权/权限错误（AUTH_*）  
`404`：资源不存在（KB/DOC/CONV not found）  
`409`：冲突（重复创建/版本冲突等）  
`429`：限流  
`500`：服务内部错误（UNEXPECTED_ERROR）  
`502/503`：外部依赖不可用（Qdrant/vLLM）  

注意：RAG “拒答”不应使用 4xx/5xx，而应返回 `200 + refusal=true`（业务可预期结果）。
