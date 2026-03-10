# STATE_AND_INTERACTION.md

## 1. 通用状态模型
每个页面或模块必须至少处理以下四态：
- `loading`
- `success`
- `empty`
- `error`

禁止只实现 `loading + success` 两态。

## 2. 知识库页面
- 管理端知识库能力拆分为两个页面：
  - `/admin/kb`：列表、筛选、编辑、删除
  - `/admin/kb/create`：独立创建知识库
- 列表加载中：显示骨架或加载态。
- 创建中：提交按钮进入 `loading`，禁止重复点击。
- 更新中：编辑弹窗 `confirmLoading` 生效。
- 删除中：必须二次确认，删除后刷新列表并清理当前选中态。

## 3. 文档入库页面
- 管理端文档能力拆分为两个页面：
  - `/admin/documents`：按知识库查看文档、当前任务和任务历史
  - `/admin/documents/upload`：独立上传文档，成功后返回管理页
- 上传中：禁止重复提交。
- 上传成功：自动进入任务跟踪。
- 任务轮询中：展示状态、阶段、进度信息。
- 任务结束：停止轮询并给出明确结果。
- 任务历史：必须可查看、取消、重试。
- 文档状态、历史任务结果、当前任务趋势应在同页可见，避免只能依赖表格逐行判断。

## 4. 问答页面
### 4.1 页面状态
- `loading`
- `success`
- `empty`
- `error`

### 4.2 发送状态
- `ask_idle`
- `ask_sending`
- `ask_streaming`
- `ask_stopping`
- `ask_failed`

### 4.3 业务状态
- `ask_answered`
- `ask_refused`

### 4.4 判定规则
- SSE `done.status=succeeded` 且 `refusal=false`：`ask_answered`
- SSE `done.status=succeeded` 且 `refusal=true`：`ask_refused`
- SSE `done.status=canceled`：回到 `ask_idle`
- HTTP 非 2xx 或 SSE `error`：`ask_failed`

## 5. 问答交互规则
- 用户通过知识库名称选择器切换知识库，不暴露 `kb_id` 输入框。
- 提交问题后，立即插入本地用户消息与助手占位消息。
- `token` 事件到达后增量拼接助手正文。
- `citation` 事件到达后增量更新引用。
- `done` 事件到达后回填 `conversation_id / message_id / user_message_id / created_at`。
- 如果 `citations` 非空，默认允许快速打开引用面板。
- 如果 `refusal=true`，显示建议块，不按接口失败处理。
- 点击助手消息打开证据弹窗。
- 证据弹窗支持按钮关闭与键盘关闭。
- 输入区必须始终可见，不被消息流挤出页面。

## 6. 会话列表规则
- 会话侧栏支持按知识库和关键字过滤。
- 允许新建、重命名、删除会话。
- 切换会话时加载最近消息页。
- 支持“加载更早消息”。
- 加载失败时不清空侧栏会话列表。

## 7. 反馈规则
- 反馈入口只对助手消息展示。
- 已提交反馈的消息应进入不可重复提交状态。
- 提交失败时允许重试。

## 8. 用户管理页面
- 管理端用户能力拆分为两个页面：
  - `/admin/users`：用户列表、状态编辑、角色配置、知识库授权
  - `/admin/users/create`：独立创建用户
- 创建用户成功后刷新列表并保留默认角色 `user`。
- 编辑用户支持修改状态、角色，可选重置密码。
- 权限弹窗支持：
  - 查看已有权限
  - 新增或更新单条权限
  - 撤销单条权限
  - 批量覆盖权限列表

## 9. 评测中心页面
- 管理端评测能力拆分为两个页面：
  - `/admin/eval`：发起评测、查询结果、查看指标
  - `/admin/eval/create`：独立设计评测集
- 创建评测集后，应自动进入最近评测集缓存。
- 发起评测必须选择评测集和知识库。
- 查询结果时同时展示：
  - 指标卡
  - 图表
  - 明细表格

## 10. 队列监控页面
- 队列统计默认 10 秒自动刷新。
- 危险操作必须二次确认。
- 结构分布、阶段对比、总量趋势、风险趋势应与指标卡同时存在。

## 11. 认证状态
- `auth_loading`
- `authenticated`
- `anonymous`

要求：
- 登录成功后跳转到 `next` 或默认首页。
- token 过期时自动刷新一次。
- 刷新失败时回到匿名态。

## 12. 近期补充
- 问答布局补充（2026-03 第五轮）：
  - 用户消息右侧，助手消息左侧。
  - 输入区固定在底部。
  - 移动端允许退化为单列消息流。
- 问答摘要补充（2026-03 第六轮）：
  - 当前会话已有消息时，可在消息区顶部显示轻量摘要图。
  - 摘要图仅基于当前会话现有消息，不引入独立接口。
- 管理端页面拆分补充（2026-03 第七轮）：
  - `/admin/users` 与 `/admin/users/create` 拆分
  - `/admin/documents` 与 `/admin/documents/upload` 拆分
  - `/admin/eval` 与 `/admin/eval/create` 拆分
