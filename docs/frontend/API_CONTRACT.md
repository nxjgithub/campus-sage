# API_CONTRACT.md — 前端接口契约说明

## 1. 基础约定
- API 前缀：`/api/v1`
- 编码：`UTF-8`
- 响应格式：JSON
- 建议读取响应头：`X-Request-ID`
- 认证方式：`Authorization: Bearer <access_token>`
- 除 `/auth/*` 与 public 知识库匿名问答外，其余接口默认需要登录

## 2. 统一错误结构
```json
{
  "error": {
    "code": "RAG_NO_EVIDENCE",
    "message": "当前知识库中未找到足够证据，无法给出可靠答案。",
    "detail": {}
  },
  "request_id": "req_xxx"
}
```

前端统一规则：
- toast 展示 `message`
- 展开详情时展示 `code`
- 调试区展示 `request_id`

## 3. 知识库接口
- `POST /kb`
  - 用途：创建知识库
  - 请求：`name` 必填，`description/visibility/config` 选填
  - `config` 常用字段：
    - `topk`
    - `threshold`
    - `rerank_enabled`
    - `max_context_tokens`
    - `min_context_chars`
    - `min_keyword_coverage`
  - 成功：返回 `KnowledgeBaseResponse`
- `GET /kb`
  - 用途：获取知识库列表
  - 成功：`items[]`
- `GET /kb/{kb_id}`
  - 用途：获取知识库详情
- `PATCH /kb/{kb_id}`
  - 用途：更新知识库说明和配置
- `DELETE /kb/{kb_id}`
  - 用途：删除知识库
  - 成功：`{"status":"deleted","request_id":"..."}`

## 4. 文档与入库接口
- `POST /kb/{kb_id}/documents`
  - 类型：`multipart/form-data`
  - 字段：`file`(必填), `doc_name`, `doc_version`, `published_at`
  - 成功：返回 `doc + job`
- `GET /kb/{kb_id}/documents`
  - 用途：文档列表
- `GET /documents/{doc_id}`
  - 用途：文档详情
- `DELETE /documents/{doc_id}`
  - 用途：删除文档
- `POST /documents/{doc_id}/reindex`
  - 用途：重建索引，返回新任务

## 5. 入库任务接口
- `GET /ingest/jobs/{job_id}`
  - 用途：任务详情与进度
  - 状态：`queued/running/succeeded/failed/canceled`
- `POST /ingest/jobs/{job_id}/cancel`
  - 用途：取消任务
- `POST /ingest/jobs/{job_id}/retry`
  - 用途：重试任务
  - 失败场景：`409 + INGEST_JOB_NOT_RETRYABLE`

## 6. 问答接口
- `POST /kb/{kb_id}/ask`
  - 请求字段：
    - 必填：`question`
    - 选填：`conversation_id/topk/threshold/rerank_enabled/filters/debug`
  - 成功字段：
    - `answer`
    - `refusal`
    - `refusal_reason`
    - `suggestions[]`
    - `citations[]`
    - `conversation_id`
    - `message_id`
    - `timing`
  - 行为补充：
    - 服务端会在上下文中附证据编号（`证据1/证据2...`）
    - 模型回答被要求输出引用标记（`[1][2]`）
    - 若模型未输出引用标记，服务端会自动补全参考编号
  - 匿名约束：
    - 当 `kb.visibility=public` 时允许匿名访问
    - 前端需支持手动输入 `kb_id` 发起问答（不依赖知识库列表）

前端强约束：
- `refusal=false`：显示答案正文与引用卡片。
- `refusal=true`：显示拒答态与建议列表，不显示“请求失败”。
- 即使 `answer` 已带 `[1][2]`，也必须仍然展示结构化 `citations[]`。
- `citations[]` 每项至少渲染：
  - `doc_name`
  - `page_start/page_end` 或 `section_path`
  - `snippet`
  - 调试模式下 `score` 可能有值，生产态可为 `null`。

## 7. 会话接口
- `GET /conversations?kb_id=&limit=&offset=`
  - 用途：会话列表
- `GET /conversations/{conversation_id}`
  - 用途：会话详情（含消息与助手引用）

前端展示约束：
- 用户消息与助手消息视觉区分。
- 助手消息若有 `timing`，支持折叠查看。
- 助手消息若有 `citations`，需可展开查看。

## 8. 反馈接口
- `POST /messages/{message_id}/feedback`
  - 请求字段：
    - `rating: "up" | "down"`
    - `reasons: string[]`
    - `comment: string | null`
    - `expected_hint: string | null`
  - 成功：`feedback_id/message_id/status`

## 9. 监控接口
- `GET /monitor/queues`
  - 用途：获取队列统计
- `POST /monitor/queues/ingest/move-dead`
  - 用途：失败任务转死信队列

## 10. 认证与用户接口
- `POST /auth/login`
  - 请求：`email/password`
  - 响应：`access_token/refresh_token/token_type/expires_in`
- `POST /auth/refresh`
  - 请求：`refresh_token`
  - 响应：同登录
- `POST /auth/logout`
  - 请求：`refresh_token`
- `GET /users/me`
  - 用途：获取当前登录用户与角色（`roles[]`）
- `GET /users`
  - 用途：管理员获取用户列表
  - 查询参数：`status/keyword/limit/offset`
  - 响应新增：`total/limit/offset`
- `POST /users`
  - 用途：管理员创建用户
  - 请求：`email/password/roles[]`
- `PATCH /users/{user_id}`
  - 用途：管理员更新用户
  - 请求：`status/roles/password`（均可选）
- `GET /users/{user_id}/kb-access`
  - 用途：管理员读取用户知识库访问权限
- `POST /users/{user_id}/kb-access`
  - 用途：管理员设置用户知识库访问权限
  - 请求：`kb_id/access_level(read|write|admin)`
- `DELETE /users/{user_id}/kb-access/{kb_id}`
  - 用途：管理员撤销单条知识库权限
- `PUT /users/{user_id}/kb-access`
  - 用途：管理员批量替换知识库权限列表
  - 请求：`items[]`
- `GET /roles`
  - 用途：管理员获取角色枚举与权限清单

前端行为约束：
- 401 时触发一次 refresh 后重试原请求；refresh 失败则清理本地 token 并跳转登录页。
- `roles` 包含 `admin` 才允许访问 `/admin/*`。
- `/app/conversations` 需登录，`/app/ask` 可匿名。

## 11. 评测接口（管理员）
- `POST /eval/sets`
  - 用途：创建评测集
- `POST /eval/runs`
  - 用途：运行评测
- `GET /eval/runs/{run_id}`
  - 用途：查询评测结果

## 12. 前端 Query Key 约定
- `["kb","list"]`
- `["kb","detail",kbId]`
- `["documents",kbId]`
- `["ingest-job",jobId]`
- `["conversation","list",params]`
- `["conversation","detail",conversationId]`
- `["monitor","queues"]`
- `["auth","me"]`
- `["users","list",status,keyword,page,pageSize]`
- `["users","kb-access",userId]`
- `["roles","list"]`

## 13. 轮询策略约定
- 入库任务轮询间隔：2 秒。
- 当状态进入 `succeeded/failed/canceled` 时停止轮询。
- 页签切后台可降频（例如 5 秒）。
