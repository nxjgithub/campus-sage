# STATE_AND_INTERACTION.md — 前端状态与交互规范

## 1. 通用状态模型
每个页面/模块必须处理以下状态：
- `idle`：初始态
- `loading`：请求中
- `success`：请求成功且有数据
- `empty`：请求成功但无数据
- `error`：请求失败

禁止直接只处理 `loading + success` 两态。

## 2. 知识库页面状态机
- `list_loading`：列表加载中
- `list_success`：列表加载成功
- `create_submitting`：创建提交中
- `update_submitting`：配置更新中
- `delete_confirming`：删除确认态

交互要求：
- 创建成功后刷新列表并高亮新建项。
- 删除成功后清理当前选择态，避免悬空引用。

## 3. 文档上传与任务状态机
- `upload_selecting`
- `uploading`
- `upload_success`
- `upload_error`
- `job_polling`
- `job_finished`
- `job_history_view`

交互要求：
- 上传中禁用重复提交按钮。
- 上传成功后自动进入任务轮询。
- 任务结束后停止轮询并给出明确结果文案。
- 必须展示任务历史面板（至少当前会话内可追溯），支持“查看/取消/重试”。

## 4. 问答页面状态机
- 页面态：
  - `loading`
  - `success`
  - `empty`
  - `error`
- 发送态：
  - `ask_idle`
  - `ask_sending`
  - `ask_streaming`
  - `ask_stopping`
  - `ask_failed`
- 业务态：
  - `ask_answered`
  - `ask_refused`

判定规则：
- SSE `done.status=succeeded` 且 `refusal=false`：`ask_answered`
- SSE `done.status=succeeded` 且 `refusal=true`：`ask_refused`
- SSE `done.status=canceled`：回到 `ask_idle`，消息标记“已取消生成”
- HTTP 非 2xx 或 SSE `error`（非取消）：`ask_failed`

## 5. 问答交互规则
- 用户在问答页通过知识库名称选择器切换知识库，不暴露 `kb_id` 输入框。
- 用户提交问题后立即插入本地“待响应消息”占位，避免界面空白。
- 流式阶段按 `token` 增量拼接助手消息正文。
- `citation` 事件到达后增量更新证据面板。
- `done` 事件到达后回填 `conversation_id/user_message_id/message_id/assistant_created_at`。
- 如果 `citations` 非空，默认展开第一条引用。
- 若答案正文包含 `[1][2]` 引用标记，前端不做正则删除，应保留原文并在下方继续展示结构化引用卡片。
- 点击答案中的引用编号应高亮并滚动到对应引用卡片。
- 如果 `refusal=true`，显示建议关键词与“去哪里查”的提示块。
- 点击助手消息后打开证据弹窗，展示引用与耗时信息。
- 证据弹窗支持右上角 `×` 关闭与键盘关闭（`Esc`/任意键）。
- 前端必须提供“停止生成”按钮，触发 `POST /chat/runs/{run_id}/cancel`。
- 断线/中断时可通过 `GET /chat/runs/{run_id}` 恢复运行态并刷新会话消息。
- 问答主界面不提供 `topk/threshold/rerank/debug` 手动控件，运行参数由后端或 KB 配置统一管理。

## 6. 会话页交互规则
- 主问答页左侧显示会话列表，支持关键字过滤。
- 列表点击会话后拉取最新消息页。
- 消息区支持“加载更早消息”（`before + limit`）。
- 会话详情加载失败时不清空左侧会话列表。
- 同一消息下的引用与耗时信息支持折叠。
- 未登录访问会话页时，跳转登录页并携带 `next` 参数。
- 会话操作支持：创建、重命名、软删除。
- 助手消息支持：重新生成、编辑后重发（切换到新分支会话）。

## 7. 反馈交互规则
- 反馈入口仅对助手消息显示。
- 用户提交反馈后按钮置灰并提示“已提交”。
- 失败时允许重试并保留已填写内容。

## 8. 监控页交互规则
- 队列统计默认 10 秒自动刷新。
- “转死信队列”操作前必须二次确认。
- 操作成功后立即刷新统计卡片。

## 8.1 用户管理页交互规则
- 创建用户成功后刷新用户列表并保留默认角色 `user`。
- 编辑用户时支持只改状态/角色，不强制重置密码。
- KB 权限弹窗支持查看已有权限并新增/更新单条权限。
- 支持撤销单条 KB 权限。
- 支持批量覆盖 KB 权限列表（全量替换）。

## 8.2 评测中心交互规则
- 评测集支持多样本编辑与创建。
- 运行评测时必须选择 `eval_set_id` 与 `kb_id`。
- 查询评测结果时展示核心指标：`recall_at_k/mrr/avg_ms/p95_ms/samples`。

## 9. 表单与验证规则
- 所有必填项实时校验并显示中文提示。
- `threshold` 限制在 `0.0 ~ 1.0` 区间。
- `topk`、`max_context_tokens` 必须是正整数。
- 上传仅允许 `pdf` 后缀。

## 10. 交互可用性细则
- 所有 destructive 操作（删除、取消）必须二次确认。
- 所有请求按钮在 `loading` 时显示加载态并禁用重复点击。
- 错误提示需展示并支持复制 `request_id`；主问答流不展示内部 ID。

## 11. 认证状态机
- `auth_loading`：应用启动后校验 token 与当前用户。
- `authenticated`：已登录，按 `roles` 控制路由与导航。
- `anonymous`：未登录，仅保留匿名可用能力（如 public KB 问答）。

交互要求：
- 登录成功后跳转到 `next` 或默认首页。
- access_token 过期时自动 refresh 一次并重放请求。
- refresh 失败时清理本地 token 并回到匿名态。

## 管理端交互补充（去 ID 化）
- 用户管理：列表按邮箱/状态/角色检索，不显示 `user_id`，权限配置使用知识库名称选择。
- 文档与入库：文档列表与任务历史默认不显示 `doc_id/job_id`，任务操作通过按钮上下文触发。
- 评测中心：运行评测与查询结果使用“最近评测集/最近运行”可读选项，不要求手输 `eval_set_id/run_id`。
- 错误排障仍以 `request_id` 为准，但仅在错误提示中出现，不在常态面板中展示。
