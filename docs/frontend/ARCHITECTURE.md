# ARCHITECTURE.md — CampusSage 前端架构设计

## 1. 架构目标
- 保持前端结构可维护：页面层薄、业务逻辑可复用、接口调用统一。
- 与后端 `FastAPI + RAG` 契约稳定对接，降低字段漂移风险。
- 对 AI 工具友好：目录职责清晰，便于小步增量开发。

## 2. 技术栈决策
- 框架：`React + Vite + TypeScript`
- 路由：`React Router`
- 服务端状态管理：`TanStack Query`
- 请求层：`Axios`
- UI 组件：`Ant Design`
- 图表：`ECharts`
- 类型契约：`openapi-typescript`
- 测试：`Vitest + React Testing Library + MSW + Playwright`

## 3. 目录结构（目标形态）
```text
frontend/
  src/
    app/
      providers/
      router/
      layouts/
    pages/
      users/
      kb/
      documents/
      ask/
      conversations/
      monitor/
    features/
      kb/
      documents/
      ingest-jobs/
      ask/
      conversations/
      feedback/
      monitor/
    shared/
      api/
      components/
      hooks/
      types/
      utils/
      constants/
      styles/
```

路由分端：
- 管理员端路由：`/admin/*`
- 用户端路由：`/app/*`
- 登录页：`/login`

管理员关键页面：
- `/admin/users`
- `/admin/kb`
- `/admin/documents`
- `/admin/eval`
- `/admin/monitor`

## 4. 分层职责
- `pages/`
  - 页面组装与布局，不直接写接口细节。
- `features/`
  - 按业务域组织组件、hooks、表单逻辑。
- `shared/api/`
  - Axios 实例、拦截器、API 方法、Query Key。
- `shared/types/`
  - OpenAPI 生成类型 + 本地补充类型。
- `shared/components/`
  - 通用 UI 组件（状态容器、引用卡片、错误提示条）。
- `shared/auth/`
  - JWT token 存储、当前用户上下文、路由守卫（`RequireAuth/RequireRole`）。

## 5. 数据流
- 用户交互触发 `feature hook`。
- hook 调用 `shared/api`。
- `TanStack Query` 负责缓存、重试、失效与轮询。
- 页面根据 query 状态渲染统一状态视图。

## 6. 接口调用规范
- 禁止组件内直接 `fetch`/`axios` 裸调。
- 所有请求走统一 `apiClient`，统一注入：
  - `X-Request-ID`（可选，前端生成）
  - `Authorization: Bearer <access_token>`（存在 token 时自动注入）
  - 超时与错误归一化处理
- 当收到 401 且存在 refresh_token 时，客户端自动调用 `/auth/refresh` 后重放一次原请求。
- 所有 API 响应类型优先使用 OpenAPI 生成定义。

## 7. 状态管理规范
- 服务端数据（KB、文档、任务、问答、会话）由 `TanStack Query` 管理。
- UI 本地状态（弹窗开关、输入值）由 React 状态管理。
- 禁止将后端实体复制为全局本地 store 再二次维护，避免双写。

## 8. 性能策略
- 列表页启用分页或懒加载。
- 入库任务页使用可控轮询（例如 2 秒，结束自动停）。
- 对会话详情与引用卡片做按需渲染。
- 避免全局大对象状态联动重渲染。

## 9. 安全与鲁棒性
- 仅允许上传后端支持后缀（当前 `pdf`）。
- 任何 HTML 文本均按纯文本渲染，不直接 `dangerouslySetInnerHTML`。
- 超时、网络错误、后端错误码分级处理并落地统一提示。

## 10. 与后端契约同步机制
- 每次后端接口变更后更新 OpenAPI 类型：
  - `openapi-typescript http://127.0.0.1:8000/openapi.json -o src/shared/types/openapi.d.ts`
- 契约变更必须同步更新：
  - `docs/frontend/API_CONTRACT.md`
  - 对应功能测试用例

## 工作台壳层补充（2026-03）
- 管理页优先复用共享工作台组件，至少包含 `OpsWorkbench`（双栏壳层）与 `OpsPane`（统一列表/表单面板），避免每页重复拼装布局。
- 当页面需要在面板头部之下插入筛选器、密度切换、统计提示时，优先通过 `OpsPane.toolbar` 承载，而不是在页面内重复拼接 `ops-pane-body` 结构。
- 路由级布局差异通过 React Router `handle.layout` 元信息表达，例如 `hideGlobalSider`，不再在布局层硬编码路径判断。
- `PortalLayout` 负责统一读取导航配置、登录态与路由元信息；页面层只关心业务内容与面板结构。
