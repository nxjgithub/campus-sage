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
- `ask_idle`
- `ask_submitting`
- `ask_answered`
- `ask_refused`
- `ask_error`

判定规则：
- HTTP 非 2xx：`ask_error`
- HTTP 200 且 `refusal=true`：`ask_refused`
- HTTP 200 且 `refusal=false`：`ask_answered`

## 5. 问答交互规则
- 用户提交问题后立即插入本地“待响应消息”占位，避免界面空白。
- 响应返回后替换占位消息并滚动到底部。
- 如果 `citations` 非空，默认展开第一条引用。
- 若答案正文包含 `[1][2]` 引用标记，前端不做正则删除，应保留原文并在下方继续展示结构化引用卡片。
- 点击答案中的引用编号应高亮并滚动到对应引用卡片。
- 如果 `refusal=true`，显示建议关键词与“去哪里查”的提示块。

## 6. 会话页交互规则
- 列表点击会话后请求详情。
- 会话详情加载失败时不清空左侧会话列表。
- 同一消息下的引用与耗时信息支持折叠。
- 未登录访问会话页时，跳转登录页并携带 `next` 参数。

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
- 所有关键结果支持 `copy`（如 `request_id`、`conversation_id`）。

## 11. 认证状态机
- `auth_loading`：应用启动后校验 token 与当前用户。
- `authenticated`：已登录，按 `roles` 控制路由与导航。
- `anonymous`：未登录，仅保留匿名可用能力（如 public KB 问答）。

交互要求：
- 登录成功后跳转到 `next` 或默认首页。
- access_token 过期时自动 refresh 一次并重放请求。
- refresh 失败时清理本地 token 并回到匿名态。
