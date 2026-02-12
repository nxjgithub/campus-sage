# TEST_STRATEGY.md — 前端测试与验收策略

## 1. 测试目标
- 确保核心业务闭环稳定可演示。
- 保证接口契约变更可被及时发现。
- 保证 AI 生成代码不会破坏关键交互。

## 2. 测试分层
- 单元测试（Vitest）
  - 工具函数
  - 状态转换函数
  - 错误映射函数
- 组件测试（React Testing Library）
  - 引用卡片渲染
  - 拒答提示块渲染
  - 上传表单校验
- 集成测试（MSW + RTL）
  - 页面级数据流与状态切换
- 端到端测试（Playwright）
  - 关键业务路径回归

## 3. 必测业务用例
- 知识库
  - 创建成功
  - 重名创建失败（`KB_ALREADY_EXISTS`）
- 文档上传
  - pdf 上传成功并进入轮询
  - 非 pdf 拒绝（`FILE_TYPE_NOT_ALLOWED`）
  - 超限拒绝（`FILE_TOO_LARGE`）
- 入库任务
  - 任务状态从 `queued/running` 到终态
  - 取消任务与重试任务分支
- 问答
  - 正常回答：`refusal=false` 且显示 `citations`
  - 拒答：`refusal=true` 且显示建议
  - 知识库不存在：`KB_NOT_FOUND`
- 会话
  - 获取会话列表
  - 查看会话详情消息
- 反馈
  - 正常提交 `up/down`
  - 消息不存在时错误提示
- 监控
  - 队列统计正常展示
  - move-dead 操作成功后刷新

## 4. 测试数据策略
- 优先使用 MSW Mock 固化边界场景。
- E2E 可连本地后端真实服务做烟雾验证。
- 固定契约样本，避免字段顺序变化导致脆弱测试。

## 5. 质量门禁（前端 DoD）
- `lint` 通过
- `typecheck` 通过
- `unit + component` 通过
- 关键 `e2e smoke` 通过
- 功能变更对应文档已更新

## 6. 推荐命令（目标工具链）
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm test:e2e`
- `pnpm build`

## 7. 发布前手工检查清单
- 所有页面在 `loading/empty/error` 下视觉无错位。
- 拒答态与错误态视觉区分明显。
- 引用卡片信息完整且可读。
- 所有错误提示可看到 `request_id`。
- 移动端窄屏下问答与引用区域可正常浏览。
