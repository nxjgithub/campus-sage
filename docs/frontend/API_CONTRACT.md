# API_CONTRACT.md — 前端接口契约说明

## 1. 基础约定
- API 前缀：`/api/v1`
- 编码：`UTF-8`
- 响应格式：JSON
- 建议读取响应头：`X-Request-ID`
- 认证方式：`Authorization: Bearer <access_token>`
- 除 `/auth/*`、public 知识库匿名问答与匿名知识库列表外，其余接口默认需要登录

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
  - 匿名：只返回 `public`
  - `user`：返回 `public/internal`
  - `manager`：返回 `public/internal`，治理端可维护这两类知识库
  - `admin`：返回全部，包括 `admin`
  - 成功：`items[]`
  - 列表项必须包含 `description/config/visibility/updated_at`；治理端列表直接用 `config.topk/config.threshold/config.rerank_enabled/config.max_context_tokens` 展示检索策略，不得在缺少 `config` 时把重排推断为 `off`
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
  - `source_uri` 只允许填写可公开访问的 http/https 官方原文地址；演示页、本地路径和占位地址不得作为“官方来源”展示
  - 成功：返回 `doc + job`
- `POST /kb/{kb_id}/documents/staged`
  - 用途：上传到暂存区，不立即入库
  - 成功：返回 `StagedDocument`
- `POST /staged-documents/{staged_doc_id}/preview`
  - 用途：生成解析预览
  - 返回：`pages/preview_blocks/assets/chunks/warnings`
  - `preview_blocks[]`：用于文档式预览，按原文顺序返回标题、段落、表格和图片结构块；该字段只影响前端预览，不替代最终入库分块。后端会先聚合同页或同章节的连续预览文本，再按语义边界生成 `chunks[]`，避免视觉行或短段落直接变成小 chunk。后端会兼容部分 DOCX 图片条目 CRC 异常但字节完整的文件，成功恢复的图片仍通过文档级 `assets[]` 返回；PDF 图片资产也会返回，若原图格式不适合浏览器预览会转为 PNG
  - `assets[].page_number`：PDF 图片所属页码；DOCX 图片无法稳定换算页码时可为 `null`
  - `chunks[].assets[]`：文本分块关联的图片资产列表；图片不做 OCR 时，仍可随命中的文本证据返回，但只作为前端复核入口，不代表生成模型已经读取图片内容
- `PATCH /staged-documents/{staged_doc_id}/chunks/{chunk_id}`
  - 用途：入库前启用/禁用分块，或修正文本文本
  - 请求：`enabled?: boolean`, `text?: string`
- `POST /staged-documents/{staged_doc_id}/commit`
  - 用途：确认预览结果并创建正式入库任务
  - 成功：返回 `doc + job`
- `GET /assets/{asset_id}`
  - 用途：读取图片资产原图；前端预览和问答引用复核时应通过统一 `apiClient` 携带认证请求 blob
  - 说明：后端可能从本地存储或 S3/MinIO 读取，但前端只依赖该鉴权代理接口
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
    - 问答页使用流式接口渲染助手回复，增量 token 到达后更新 Markdown 聊天框
    - 服务端会在上下文中附证据编号（`证据1/证据2...`）
    - 模型回答被要求输出引用标记（`[1][2]`）
    - 若模型未输出引用标记，服务端会自动补全参考编号
  - 匿名约束：
    - 当 `kb.visibility=public` 时允许匿名访问
    - 前端通过知识库列表选择目标知识库，不向用户暴露 `kb_id` 手动输入
  - 失败：参数非法时返回 `400 + VALIDATION_FAILED`
  - 生成失败：若后端返回 `RAG_MODEL_FAILED`，表示正常回答未能调用生成模型或模型未返回有效内容；前端按接口失败展示，不得当作 `refusal=true` 业务拒答。

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
  - 若存在可信 `source_uri`，应提供“官方来源”跳转入口；`/demo/campus-sage` 等占位来源不得展示为官方来源
  - 若存在 `assets[]`，应在答案正文下方集中渲染去重后的图片缩略图，并提供打开原图能力；缩略图是证据复核材料，不应让用户误解为模型已直接分析原图
  - 若只存在旧字段 `asset_id/asset_url`，应兼容展示图片资产编号和“查看原图”入口，并通过 `asset_url` 拉取图片 blob 后预览
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
  - 隐私约束：只返回当前登录用户自己的会话；管理员在问答视角也不得看到其他用户会话
- `GET /conversations/{conversation_id}`
  - 用途：会话详情（含消息、助手引用、消息级 `request_id`、拒答后的 `suggestions/next_steps`）
- `PATCH /conversations/{conversation_id}`
  - 用途：重命名会话
- `DELETE /conversations/{conversation_id}`
  - 用途：软删除会话
- `GET /conversations/{conversation_id}/messages?before=&limit=`
  - 用途：历史消息分页
  - 返回：`items/has_more/next_before`
  - 消息项补充：消息项返回 `parent_message_id/edited_from_message_id`，助手消息可返回消息级 `request_id`，用于历史回放排障展示

前端展示约束：
- 会话详情、消息分页、继续追问、反馈、重新生成和编辑后重发遇到 `AUTH_FORBIDDEN + 无权访问该会话` 时，按失效会话处理：刷新会话列表、清空当前会话上下文，并保留用户刚输入的问题。
- 用户消息与助手消息视觉区分。
- 助手消息若 `refusal=true` 且存在 `next_steps`，历史会话中也必须渲染同一套下一步建议卡片。
- 助手消息若同时带 `suggestions[]`，历史会话中也必须作为兼容性补充说明一起展示。
- 助手消息中的 `refusal_reason` 必须先映射为中文展示，不直接暴露原始后端码。
- 助手消息若带 `request_id`，历史会话中也必须支持复制查看。
- 重新生成产生多个同父级助手消息时，问答主线程只展示最新助手消息，避免同一问题重复回答。
- 历史会话中的 `check_official_source` 建议应可直接打开；`search_keyword/rewrite_question/add_context` 等文本型建议至少应支持复制。
- 助手消息正文区域用于阅读和复制，不绑定整条消息点击事件；前端应通过引用编号、图片预览或“查看引用/查看证据详情”图标按钮打开证据弹窗，弹窗内展示 `timing/citations`。
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
- `POST /monitor/queues/ingest/cleanup-stale-started`
  - 用途：只清理过期 started registry 记录，保留任务本体和其他队列状态
- `GET /monitor/runtime`
  - 用途：获取数据库 schema、关键服务开关、上传配置、安全风险与 RAG 运行指标
  - 响应必须包含 `request_id`，失败时错误提示继续展示 `request_id`

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
- 流式问答使用 `fetch` 读取 SSE，也必须遵循同一条 401 refresh 规则；重试成功后继续按 SSE 事件更新消息。
- `roles` 包含 `admin` 或 `manager` 才允许访问 `/admin/*`；`manager` 管理端不展示用户管理入口，且直接访问 `/admin/users*` 应重定向。
- `roles` 包含 `manager` 时前端默认工作台为 `/admin/kb`，但知识库可见性选项不得提供 `admin`。
- `/app/conversations` 需登录，`/app/ask` 可匿名。

## 11. 评测接口（管理员）
- `GET /eval/sets`
  - 用途：列出服务端评测集，运行页优先使用该列表，本地最近记录只作为兜底
- `POST /eval/sets`
  - 用途：创建评测集
- `GET /eval/runs`
  - 用途：列出服务端评测运行
  - 查询参数：`limit/offset`
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
- `["monitor","runtime"]`
- `["eval","sets"]`
- `["eval","runs"]`
- `["auth","me"]`
- `["users","list",status,keyword,page,pageSize]`
- `["users","kb-access",userId]`
- `["roles","list"]`

## 运行时诊断补充
- `GET /monitor/runtime` 的 `services` 字段包含 `vector_backend`、`embedding_backend`、`rerank_backend`、`vllm_enabled`、`ingest_queue_enabled`，用于前端展示当前问答链路实际加载的后端配置。

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
