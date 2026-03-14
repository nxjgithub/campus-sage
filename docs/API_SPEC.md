# API_SPEC.md — CampusSage API 规范（MVP → 可扩展）

本文档定义 CampusSage（CSage）后端 API 规范（FastAPI）。目标：接口形状稳定、错误格式统一、支持 RAG 证据链与可观测性。

通用约定：
`API 前缀`：`/api/v1`  
`响应格式`：JSON  
`编码`：UTF-8  
`request_id`：建议每个响应返回 `request_id`，并在 Header 返回 `X-Request-ID`

认证约定：
- 除 `/auth/*` 接口外，默认需要 `Authorization: Bearer <access_token>`  
- 若知识库 `visibility=public`，问答接口可匿名访问


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
`source_uri: str | null`  
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
`next_steps: List[{action, label, detail, value}]`  
其中 `action` 当前允许值：`search_keyword | rewrite_question | add_context | check_official_source | verify_kb_scope`
`citations: List[Citation]`  
`conversation_id: str | null`  
`message_id: str | null`  
`user_message_id: str | null`  
`assistant_created_at: str | null`  
`timing: object | null`（retrieve_ms/rerank_ms/context_ms/generate_ms/total_ms）  
`request_id: str | null`

### 1.6 User
`user_id: str`  
`email: str`  
`status: str`（"active" | "disabled" | "deleted"）  
`roles: List[str]`  
`created_at: str`  
`updated_at: str`  
`last_login_at: str | null`

### 1.7 TokenResponse
`access_token: str`  
`refresh_token: str`  
`token_type: str`（"bearer"）  
`expires_in: int`  
`request_id: str | null`

### 1.8 ChatRun
`run_id: str`  
`kb_id: str | null`  
`user_id: str | null`  
`conversation_id: str | null`  
`user_message_id: str | null`  
`assistant_message_id: str | null`  
`status: str`（"running" | "succeeded" | "failed" | "canceled"）  
`cancel_flag: bool`  
`started_at: str`  
`finished_at: str | null`  
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
    "max_context_tokens": 3000,
    "min_evidence_chunks": 1,
    "min_context_chars": 20,
    "min_keyword_coverage": 0.3
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
  "config": {"topk": 5, "threshold": 0.25, "rerank_enabled": false, "max_context_tokens": 3000, "min_evidence_chunks": 1, "min_context_chars": 20, "min_keyword_coverage": 0.3},
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
  "config": {"topk": 8, "threshold": 0.22, "rerank_enabled": true, "min_evidence_chunks": 1, "min_keyword_coverage": 0.3}
}
```

说明：
- `config` 支持局部更新；未传入的配置字段保持原值不变。
- 示例：仅更新阈值可传 `{"config": {"threshold": 0.22}}`。
- `config` 字段约束：
  - `topk`：`1~50`
  - `threshold`：`0~1`
  - `max_context_tokens`：`>=1`
  - `min_evidence_chunks`：`>=1` 且不能大于 `topk`
  - `min_context_chars`：`>=1`
  - `min_keyword_coverage`：`0~1`
- 参数不合法时返回 `400 + VALIDATION_FAILED`。

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
`source_uri`：可选，要求为 `http/https` 官方来源链接

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
### 4.1 发起问答（同步）
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
  "next_steps": [],
  "citations": [
    {
      "citation_id": 1,
      "doc_id": "doc_123",
      "doc_name": "教务管理规定.pdf",
      "doc_version": "2025-09",
      "published_at": "2025-09-01",
      "source_uri": "https://example.edu/academic/policy",
      "page_start": 12,
      "page_end": 12,
      "section_path": "考试管理/补考规定",
      "chunk_id": "chunk_a",
      "snippet": "……补考申请条件包括……",
      "score": 0.78
    }
  ],
  "conversation_id": "conv_001",
  "message_id": "msg_790",
  "user_message_id": "msg_789",
  "assistant_created_at": "2026-02-07T10:10:02Z",
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
  "next_steps": [
    {
      "action": "search_keyword",
      "label": "补充关键词",
      "detail": "将问题补充为“事项 + 对象 + 条件/时间/材料”后重新提问。",
      "value": "补考申请条件"
    },
    {
      "action": "check_official_source",
      "label": "查看官方来源",
      "detail": "优先核对学校官网、教务处或学院公告中的最新制度原文。",
      "value": "https://example.edu/academic/policy"
    }
  ],
  "citations": [],
  "conversation_id": "conv_001",
  "message_id": "msg_792",
  "user_message_id": "msg_791",
  "assistant_created_at": "2026-02-07T10:12:02Z",
  "timing": {"retrieve_ms": 35, "rerank_ms": 0, "context_ms": 8, "generate_ms": 120, "total_ms": 180},
  "request_id": "req_xxx"
}
```
说明：`debug=true` 时返回 `citations.score`，否则可为 `null`。  
约束：`citations` 与 `refusal` 规则必须符合 `docs/RAG_CONTRACT.md`。
- 运行时参数约束：
  - `topk`（可选）：`1~50`
  - `threshold`（可选）：`0~1`
- 参数不合法时返回 `400 + VALIDATION_FAILED`。
- 兼容性：若知识库中存在历史非法配置值（如超范围或错误类型），服务端会自动回退到系统默认值继续执行。

### 4.2 发起问答（流式 SSE）
`POST /api/v1/kb/{kb_id}/ask/stream`  
`Content-Type: application/json`  
`Accept: text/event-stream`

请求体与 `POST /api/v1/kb/{kb_id}/ask` 一致。

SSE 事件约定（每个事件都必须带 `request_id`）：
- `start`：流式启动
- `ping`：心跳事件（保活）
- `token`：增量文本片段（`delta`）
- `citation`：单条引用对象
- `refusal`：拒答结果（包含 `answer/refusal_reason/suggestions/next_steps`）
- `done`：流结束（`status` 为 `succeeded/failed/canceled`）
- `error`：流内错误（包括取消信号）

事件示例：
```text
event: start
data: {"run_id":"run_123","conversation_id":"conv_001","request_id":"req_xxx"}

event: token
data: {"run_id":"run_123","delta":"根据教务管理规定","request_id":"req_xxx"}

event: ping
data: {"run_id":"run_123","request_id":"req_xxx"}

event: citation
data: {"run_id":"run_123","citation":{"citation_id":1,"doc_id":"doc_123","doc_name":"教务管理规定.pdf","doc_version":"2025-09","published_at":"2025-09-01","source_uri":"https://example.edu/academic/policy","page_start":12,"page_end":12,"section_path":"考试管理/补考规定","chunk_id":"chunk_a","snippet":"……补考申请条件包括……","score":null},"request_id":"req_xxx"}

event: done
data: {"run_id":"run_123","status":"succeeded","conversation_id":"conv_001","user_message_id":"msg_789","message_id":"msg_790","assistant_created_at":"2026-02-07T10:10:02Z","refusal":false,"timing":{"retrieve_ms":45,"rerank_ms":0,"context_ms":12,"generate_ms":380,"total_ms":450},"request_id":"req_xxx"}
```
说明：
- 服务端会周期性发送 `ping` 事件，降低中间层静默断连风险。
- 连接断开后，服务端会标记对应 run 取消（`status=canceled`）。

### 4.3 获取运行状态
`GET /api/v1/chat/runs/{run_id}`

响应示例：
```json
{
  "run_id": "run_123",
  "kb_id": "kb_123",
  "conversation_id": "conv_001",
  "user_message_id": "msg_789",
  "assistant_message_id": "msg_790",
  "status": "running",
  "cancel_flag": false,
  "started_at": "2026-02-07T10:10:00Z",
  "finished_at": null,
  "request_id": "req_xxx"
}
```
说明：仅允许 run 归属用户（或管理员）查询。

### 4.4 取消流式生成
`POST /api/v1/chat/runs/{run_id}/cancel`

响应示例：
```json
{
  "run_id": "run_123",
  "status": "canceled",
  "cancel_flag": true,
  "request_id": "req_xxx"
}
```
说明：
- 仅允许 run 归属用户（或管理员）取消。
- 若 run 已结束，接口仍可调用，返回当前状态并设置/保持 `cancel_flag`（幂等语义）。

### 4.5 重新生成回答
`POST /api/v1/messages/{message_id}/regenerate`

请求示例：
```json
{
  "topk": 8,
  "threshold": 0.22,
  "rerank_enabled": true,
  "filters": {"doc_ids": ["doc_123"], "published_after": "2024-01-01"},
  "debug": false
}
```
说明：
- `message_id` 可是用户消息或助手消息。
- 若传助手消息，系统会回溯到该消息前最近一条用户消息作为重生成问题。
- 返回 `AskResponse`，`conversation_id` 与来源会话一致，`user_message_id` 复用来源用户消息，`message_id` 为新助手消息。

### 4.6 编辑后重发（新分支会话）
`POST /api/v1/messages/{message_id}/edit-and-resend`

请求示例：
```json
{
  "question": "编辑后的问题：补考申请条件",
  "topk": 8,
  "threshold": 0.22,
  "rerank_enabled": true,
  "filters": {"doc_ids": ["doc_123"]},
  "debug": false
}
```
说明：
- 服务端会创建新会话分支。
- 编辑后的用户消息会记录 `edited_from_message_id` 指向原消息。
- 返回 `AskResponse`，其中 `conversation_id` 为新分支会话 ID。


## 5. 会话与消息接口
### 5.1 创建空会话
`POST /api/v1/conversations`

请求示例：
```json
{
  "kb_id": "kb_123",
  "title": "补考咨询"
}
```

响应示例：
```json
{
  "conversation_id": "conv_001",
  "kb_id": "kb_123",
  "title": "补考咨询",
  "created_at": "2026-02-07T10:10:00Z",
  "updated_at": "2026-02-07T10:10:00Z",
  "request_id": "req_xxx"
}
```

### 5.2 获取会话列表（侧栏场景）
`GET /api/v1/conversations`

可选查询参数：
- `kb_id: str`
- `keyword: str`（按标题与消息内容模糊匹配）
- `cursor: str`（格式：`<updated_at>|<conversation_id>`）
- `limit: int`（1~100，默认 20）
- `offset: int`（默认 0，兼容保留）

响应示例：
```json
{
  "items": [
    {
      "conversation_id": "conv_001",
      "kb_id": "kb_123",
      "title": "补考咨询",
      "last_message_preview": "补考申请需要满足什么条件？",
      "last_message_at": "2026-02-07T10:10:02Z",
      "updated_at": "2026-02-07T10:10:02Z"
    }
  ],
  "total": 12,
  "next_cursor": "2026-02-07T10:10:02Z|conv_001",
  "request_id": "req_xxx"
}
```

### 5.3 获取会话详情（全量消息）
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
      "next_steps": [],
      "timing": {"retrieve_ms": 45, "rerank_ms": 0, "context_ms": 12, "generate_ms": 380, "total_ms": 450},
      "created_at": "2026-02-07T10:10:02Z"
    }
  ],
  "request_id": "req_xxx"
}
```
说明：`assistant` 消息包含 `citations/refusal/refusal_reason/next_steps/timing` 字段，`user` 消息这些字段为 `null` 或省略。

### 5.4 重命名会话
`PATCH /api/v1/conversations/{conversation_id}`

请求示例：
```json
{"title": "补考咨询（已确认）"}
```

响应结构与“创建空会话”一致。

### 5.5 软删除会话
`DELETE /api/v1/conversations/{conversation_id}`

响应示例：
```json
{
  "conversation_id": "conv_001",
  "status": "deleted",
  "request_id": "req_xxx"
}
```

### 5.6 分页获取会话消息
`GET /api/v1/conversations/{conversation_id}/messages?before=<message_id>&limit=50`

说明：
- 首次拉取不传 `before`。
- `before` 表示“取该消息之前”的历史消息。
- 默认 `limit=50`，最大 100。

响应示例：
```json
{
  "items": [
    {
      "message_id": "msg_100",
      "role": "user",
      "content": "补考申请条件是什么？",
      "created_at": "2026-02-07T10:08:00Z"
    },
    {
      "message_id": "msg_101",
      "role": "assistant",
      "content": "根据规定……[1]",
      "citations": [],
      "refusal": false,
      "refusal_reason": null,
      "next_steps": [],
      "timing": {"retrieve_ms": 40, "rerank_ms": 0, "context_ms": 9, "generate_ms": 210, "total_ms": 259},
      "created_at": "2026-02-07T10:08:02Z"
    }
  ],
  "has_more": true,
  "next_before": "msg_100",
  "request_id": "req_xxx"
}
```


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

## 6.2 认证（Auth）
### 6.2.1 登录
`POST /api/v1/auth/login`

请求示例：
```json
{"email": "admin@example.com", "password": "Admin1234"}
```

响应示例：
```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt_xxx",
  "token_type": "bearer",
  "expires_in": 3600,
  "request_id": "req_xxx"
}
```

### 6.2.2 刷新令牌
`POST /api/v1/auth/refresh`

请求示例：
```json
{"refresh_token": "rt_xxx"}
```

### 6.2.3 退出登录
`POST /api/v1/auth/logout`

请求示例：
```json
{"refresh_token": "rt_xxx"}
```

## 6.3 用户（Users）
### 6.3.1 获取当前用户
`GET /api/v1/users/me`

响应示例：
```json
{
  "user_id": "user_001",
  "email": "admin@example.com",
  "status": "active",
  "roles": ["admin"],
  "created_at": "2026-02-12T10:00:00Z",
  "updated_at": "2026-02-12T10:00:00Z",
  "last_login_at": "2026-02-12T10:10:00Z",
  "request_id": "req_xxx"
}
```

### 6.3.2 创建用户（管理员）
`POST /api/v1/users`

请求示例：
```json
{"email": "user@example.com", "password": "User1234", "roles": ["user"]}
```

### 6.3.3 获取用户列表（管理员）
`GET /api/v1/users?status=&keyword=&limit=&offset=`

参数说明：
- `status`：可选，`active` / `disabled` / `deleted`
- `keyword`：可选，模糊匹配邮箱或用户ID
- `limit`：可选，默认 20
- `offset`：可选，默认 0

响应示例：
```json
{
  "items": [
    {
      "user_id": "user_001",
      "email": "admin@example.com",
      "status": "active",
      "roles": ["admin"],
      "created_at": "2026-02-12T10:00:00Z"
    }
  ],
  "total": 12,
  "limit": 20,
  "offset": 0,
  "request_id": "req_xxx"
}
```

### 6.3.4 更新用户（管理员）
`PATCH /api/v1/users/{user_id}`

请求示例：
```json
{"status": "disabled", "roles": ["user"]}
```

### 6.3.5 设置用户知识库权限（管理员）
`POST /api/v1/users/{user_id}/kb-access`

请求示例：
```json
{"kb_id": "kb_123", "access_level": "write"}
```
说明：`access_level` 取值 `read` / `write` / `admin`

### 6.3.6 获取用户知识库权限（管理员）
`GET /api/v1/users/{user_id}/kb-access`

### 6.3.7 撤销用户知识库权限（管理员）
`DELETE /api/v1/users/{user_id}/kb-access/{kb_id}`

响应示例：
```json
{"user_id": "user_001", "kb_id": "kb_123", "status": "deleted", "request_id": "req_xxx"}
```

### 6.3.8 批量更新用户知识库权限（管理员）
`PUT /api/v1/users/{user_id}/kb-access`

请求示例：
```json
{
  "items": [
    {"kb_id": "kb_123", "access_level": "read"},
    {"kb_id": "kb_456", "access_level": "admin"}
  ]
}
```
说明：该接口会全量替换该用户的权限列表。

### 6.3.9 获取角色列表（管理员）
`GET /api/v1/roles`

响应示例：
```json
{
  "items": [
    {"name": "admin", "permissions": ["*"]},
    {"name": "user", "permissions": ["kb.read", "rag.ask", "conversation.read", "conversation.write", "message.write", "feedback.write"]}
  ],
  "request_id": "req_xxx"
}
```

## 7. 评测（Eval）
说明：支持通过 API 进行评测集创建与评测运行。

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

参数约束：
- `topk`：`1~50`
- `threshold`（可选）：`0~1`
- 参数不合法时返回 `400 + VALIDATION_FAILED`。

### 7.3 获取评测结果
`GET /api/v1/eval/runs/{run_id}`

响应建议包含：`recall_at_k`、`mrr`、`avg_ms`、`p95_ms`

响应示例：
```json
{
  "run_id": "erun_001",
  "eval_set_id": "es_001",
  "kb_id": "kb_123",
  "topk": 5,
  "threshold": 0.25,
  "rerank_enabled": false,
  "metrics": {
    "recall_at_k": 0.8,
    "mrr": 0.6,
    "avg_ms": 120,
    "p95_ms": 240,
    "samples": 10
  },
  "created_at": "2026-02-12T10:00:00Z",
  "request_id": "req_xxx"
}
```


## 8. 监控（Queue Monitor，可选）
说明：监控路由统一挂载在 `/api/v1/monitor/*`，不再提供重复的 `/monitor/*` 入口。

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

### 8.3 获取运行时诊断摘要
`GET /api/v1/monitor/runtime`

说明：
- 仅返回排障所需的配置摘要，不返回密钥原文。
- 该接口用于确认当前服务实际加载的数据库 schema 版本、关键开关和上传配置。

响应示例：
```json
{
  "app_env": "local",
  "log_level": "INFO",
  "debug_mode": false,
  "enable_swagger": true,
  "database": {
    "backend": "sqlite",
    "target": "./data/csage.db",
    "schema_version": 4
  },
  "services": {
    "vector_backend": "qdrant",
    "embedding_backend": "http",
    "vllm_enabled": false,
    "ingest_queue_enabled": false
  },
  "upload": {
    "max_mb": 30,
    "allowed_exts": ["pdf", "docx", "html", "htm", "md", "txt"]
  },
  "security": {
    "jwt_default_secret": false
  },
  "warnings": [],
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

## 多类型上传补充（2026-03 第三轮）
- `POST /api/v1/kb/{kb_id}/documents` 首批正式支持：`pdf`、`docx`、`html`、`htm`、`md`、`txt`。
- 非支持后缀仍返回 `400 + FILE_TYPE_NOT_ALLOWED`。
- 引用定位规则保持不变：`pdf` 优先页码，其余类型优先 `section_path + snippet`。
