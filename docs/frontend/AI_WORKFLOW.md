# AI_WORKFLOW.md — 前端 AI 协作工作流（Codex/同类工具）

## 1. 目标
定义 AI 参与前端开发时的硬规则，确保产出可运行、可测试、可维护、可追溯。

## 2. 强制阅读顺序
每次任务开始前，AI 必须先阅读：
1. `docs/frontend/FRONTEND_OVERVIEW.md`
2. `docs/frontend/ARCHITECTURE.md`
3. `docs/frontend/API_CONTRACT.md`
4. `docs/frontend/STATE_AND_INTERACTION.md`
5. `docs/frontend/UI_RULES.md`
6. `docs/frontend/ERROR_HANDLING.md`
7. `docs/frontend/TEST_STRATEGY.md`

未阅读不得直接改代码。

## 3. 任务拆分规则
- 一次只完成一个明确任务。
- 每个任务必须包含：
  - 目标页面或模块
  - 影响接口
  - 预期输入输出
  - 验收标准

禁止“一次性重构全站”。

## 4. 编码边界规则
- 只能修改本任务相关文件，不得顺手改无关模块。
- 禁止随意调整目录结构。
- 禁止新增与后端契约冲突的字段。
- 公共 API 调用必须走统一 `shared/api`。

## 5. UI 与交互规则
- 必须遵守 `UI_RULES.md` 中设计令牌与排版规范。
- 必须实现 `loading/success/empty/error` 四态。
- 问答模块必须区分：
  - `error`
  - `refusal=true`

## 6. 测试与验证规则
- 改动核心交互必须补对应测试。
- 最低验证要求：
  - 类型检查通过
  - lint 通过
  - 相关测试通过
- 无法执行命令时，必须说明原因与影响范围。

## 7. 文档同步规则
出现以下任一情况必须更新文档：
- 页面行为变更
- API 调用方式变更
- 错误处理策略变更
- 视觉规范变更

优先更新文件：
- `docs/frontend/API_CONTRACT.md`
- `docs/frontend/STATE_AND_INTERACTION.md`
- `docs/frontend/ERROR_HANDLING.md`

## 8. 提交流程建议
- 提交信息使用 Conventional Commits：
  - `feat(frontend): ...`
  - `fix(frontend): ...`
  - `docs(frontend): ...`
  - `test(frontend): ...`
- 每次提交附带简短变更说明：
  - 改了什么
  - 为什么改
  - 如何验证

## 9. 禁止行为
- 不经说明直接删除页面或 API 调用。
- 以“临时写死数据”替代真实接口而不标注。
- 忽略后端错误码直接统一提示“失败”。
- 在未更新文档情况下引入新交互约定。

## 10. AI 任务完成定义（前端）
- 功能按文档实现且可运行。
- 错误处理与状态机行为正确。
- 测试与静态检查通过。
- 文档同步完成。
