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
- 错误提示中展示 `request_id`（用于排障）

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
  - `config` 取值约束：
    - `topk`: `1~50`
    - `threshold`: `0~1`
    - `max_context_tokens`: `>=1`
    - `min_evidence_chunks`: `>=1` 且不能大于 `topk`
    - `min_context_chars`: `>=1`
    - `min_keyword_coverage`: `0~1`
  - 成功：返回 `KnowledgeBaseResponse`
- `GET /kb`
  - 用途：获取知识库列表
  - 成功：`items[]`
- `GET /kb/{kb_id}`
  - 用途：获取知识库详情
- `PATCH /kb/{kb_id}`
  - 用途：更新知识库说明和配置
  - 说明：`config` 支持局部更新，未传字段保持原值不变
  - 失败：参数非法时返回 `400 + VALIDATION_FAILED`
- `DELETE /kb/{kb_id}`
  - 用途：删除知识库
  - 成功：`{"status":"deleted","request_id":"..."}`

## 4. 文档与入库接口
- `POST /kb/{kb_id}/documents`
  - 类型：`multipart/form-data`
  - 字段：`file`(必填), `doc_name`, `doc_version`, `published_at`, `source_uri`
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
    - 选填：`conversation_id`（`topk/threshold/rerank_enabled/debug` 等运行参数由后端或知识库配置托管）
    - 参数约束：`topk` 为 `1~50`，`threshold` 为 `0~1`
  - 成功字段：
    - `answer`
    - `refusal`
    - `refusal_reason`
    - `suggestions[]`
    - `next_steps[]`
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
    - 前端通过知识库列表选择目标知识库，不向用户暴露 `kb_id` 手动输入
  - 失败：参数非法时返回 `400 + VALIDATION_FAILED`

前端强约束：
- `refusal=false`：显示答案正文与引用卡片。
- `refusal=true`：显示拒答态与建议列表，不显示“请求失败”。
- `refusal=true` 时优先渲染 `next_steps[]`，`suggestions[]` 作为兼容性兜底文本保留。
- `next_steps[].action` 当前仅允许：
  - `search_keyword`
  - `rewrite_question`
  - `add_context`
- `check_official_source`
- `verify_kb_scope`
- 建议动作映射：
  - `search_keyword` / `rewrite_question` / `add_context`：回填输入框，帮助用户继续追问
  - `check_official_source`：若 `next_steps[].value` 为 http/https 链接，则直接打开官方来源；否则再回退到文档治理入口或提示用户查看官网
  - `verify_kb_scope`：优先跳到已有文档治理入口；若当前门户无该入口，则提示用户查看官网或联系管理员
- 即使 `answer` 已带 `[1][2]`，也必须仍然展示结构化 `citations[]`。
- 问答主界面不展示内部标识（如 `kb_id/run_id/conversation_id/message_id`）。
- `citations[]` 每项至少渲染：
  - `doc_name`
  - `page_start/page_end` 或 `section_path`
  - `snippet`
  - 若存在 `source_uri`，应提供“官方来源”跳转入口
  - 调试模式下 `score` 可能有值，生产态可为 `null`。

- `POST /kb/{kb_id}/ask/stream`
  - 类型：SSE（`Accept: text/event-stream`）
  - 事件序列：`start -> ping/token/citation/refusal -> done`
  - 关键事件字段：
    - `start`: `run_id/conversation_id/request_id`
    - `token`: `delta`
    - `citation`: `citation`
    - `refusal`: `answer/refusal_reason/suggestions/next_steps`
    - `done`: `status/conversation_id/user_message_id/message_id/assistant_created_at`
    - `error`: `code/message/request_id`
  - 前端规则：
    - `refusal` 仍属于业务成功态，不显示接口失败。
    - `ping` 仅保活，不更新消息正文。
    - `done.status=canceled` 时将消息标记为“已取消生成”。

- `GET /chat/runs/{run_id}`
  - 用途：断线恢复时查询运行态
  - 关键字段：`status/cancel_flag/conversation_id/user_message_id/assistant_message_id`

- `POST /chat/runs/{run_id}/cancel`
  - 用途：取消流式生成
  - 说明：幂等，前端在流式进行中允许重复触发

- `POST /messages/{message_id}/regenerate`
  - 用途：对既有消息重新生成答案（同会话）

- `POST /messages/{message_id}/edit-and-resend`
  - 用途：编辑问题后重发，生成新分支会话
  - 关键前端行为：成功后切换到返回的 `conversation_id`

## 7. 会话接口
- `POST /conversations`
  - 用途：创建空会话
- `GET /conversations?kb_id=&keyword=&cursor=&limit=&offset=`
  - 用途：会话列表（侧栏）
  - 返回增强：`total/next_cursor/last_message_preview/last_message_at`
- `GET /conversations/{conversation_id}`
  - 用途：会话详情（含消息、助手引用与拒答后的 `next_steps`）
- `PATCH /conversations/{conversation_id}`
  - 用途：重命名会话
- `DELETE /conversations/{conversation_id}`
  - 用途：软删除会话
- `GET /conversations/{conversation_id}/messages?before=&limit=`
  - 用途：历史消息分页
  - 返回：`items/has_more/next_before`

前端展示约束：
- 用户消息与助手消息视觉区分。
- 助手消息若 `refusal=true` 且存在 `next_steps`，历史会话中也必须渲染同一套下一步建议卡片。
- 助手消息点击后打开证据弹窗，弹窗内展示 `timing/citations`。
- 问答主界面必须支持“加载更早消息”。

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
  - 参数约束：`topk` 为 `1~50`，`threshold`（可选）为 `0~1`
  - 失败：参数非法时返回 `400 + VALIDATION_FAILED`
- `GET /eval/runs/{run_id}`
  - 用途：查询评测结果

## 12. 前端 Query Key 约定
- `["kb","list"]`
- `["kb","detail",kbId]`
- `["documents",kbId]`
- `["ingest-job",jobId]`
- `["conversation","list",params]`
- `["conversation","messages",conversationId,before,limit]`
- `["chat","run",runId]`
- `["monitor","queues"]`
- `["auth","me"]`
- `["users","list",status,keyword,page,pageSize]`
- `["users","kb-access",userId]`
- `["roles","list"]`

## 13. 轮询策略约定
- 入库任务轮询间隔：2 秒。
- 当状态进入 `succeeded/failed/canceled` 时停止轮询。
- 页签切后台可降频（例如 5 秒）。

## 管理端展示约束补充
- 前端在管理端调用涉及 ID 的接口时，ID 必须由已选择对象隐式携带，不要求用户感知或手动输入。
- 可见文案优先展示业务可读字段（`name/email/doc_name/status/created_at`），内部 ID 仅用于接口路径与缓存键。

## 文档上传补充（2026-03 第四轮）
- `POST /kb/{kb_id}/documents` 首批支持 `pdf/docx/html/htm/md/txt`。
- 前端上传控件应根据支持集展示明确提示，不再写死“仅 PDF”。
- 不支持的后缀继续按 `FILE_TYPE_NOT_ALLOWED` 处理。
# 2026-03 补充：异常展示契约

- 前端对后端统一错误结构做二次加工后再展示，不直接把 `error.code` 作为用户主文案。
- `toast` 与页内错误卡片的主文案优先使用前端错误码映射；未命中时回退到 `error.message`。
- `error.code` 与 `request_id` 保留为排障信息，用于复制与定位，不作为主提示文案。
