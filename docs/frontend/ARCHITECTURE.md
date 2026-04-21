# ARCHITECTURE.md

## 1. 架构目标
- 页面层保持薄，业务逻辑集中。
- API 调用统一，避免散落在组件中。
- 状态清晰，可维护，可测试。
- 与后端 `FastAPI + RAG` 契约稳定对接。

## 2. 技术栈
- React
- Vite
- TypeScript
- React Router
- TanStack Query
- Axios
- Ant Design
- Vitest + React Testing Library

当前图表优先使用轻量原生组件，不引入额外重量级图表依赖。

## 3. 目标目录
```text
frontend/
  src/
    app/
      layouts/
      providers/
      router/
    pages/
      ask/
      kb/
      documents/
      eval/
      users/
      monitor/
    shared/
      api/
      auth/
      components/
      constants/
      hooks/
      styles/
      types/
      utils/
```

## 4. 分层职责
- `pages/`
  - 页面组装、布局组织、页面级状态协调
- `shared/api/`
  - Axios 实例
  - 接口方法
  - 错误归一化
- `shared/components/`
  - 通用卡片、提示、确认按钮、图表、工作台壳层
- `shared/auth/`
  - token 管理
  - 当前用户上下文
  - 登录态恢复
- `shared/styles/`
  - 全局视觉规范与页面壳层样式

## 5. 数据流
1. 用户操作触发页面事件。
2. 页面通过 `shared/api` 或 `TanStack Query` 发起请求。
3. 响应结果进入 Query 缓存或页面本地状态。
4. 页面依据状态渲染 `loading / success / empty / error`。

## 6. 接口调用规则
- 禁止在业务组件里直接裸写 `fetch` 或新的 `axios` 实例。
- 所有请求统一走 `apiClient`。
- 401 时允许统一刷新 token 后重放请求。
- 错误统一转换为前端可消费的错误结构。

## 7. 布局规则
- 管理端优先复用：
  - `PortalLayout`
  - `CompactPageHero`
  - `OpsWorkbench`
  - `OpsPane`
- 页面差异通过路由元信息表达，不在壳层硬编码大量路径判断。
- 用户端问答页允许隐藏全局侧栏，使用聊天专属布局。
- `/app/ask` 是用户端首屏主路径，允许绕过全局门户壳层直接加载聊天工作台，避免把低频侧栏导航和管理端依赖压到问答首屏。

## 8. 图表策略
- 先用轻量原生图表组件完成：
  - 分布图
  - 对比图
  - 趋势图
- 如果未来确实需要复杂交互图表，再评估引入专用图库。

## 9. 性能与鲁棒性
- 列表页优先分页或限制条数。
- 长轮询与任务查询必须自动停止。
- 避免把服务端实体再复制到额外全局 store 中重复维护。
- 对会话、引用、任务历史等按需渲染。
- 路由级页面、登录页和门户布局必须保持懒加载；低频管理页不得进入初始入口包。
- Vite 构建只预加载入口必要依赖，动态路由依赖应由路由访问时再加载。
- Ant Design 入口只保留 `ConfigProvider`、`App` 等必要核心能力，页面组件依赖由对应路由 chunk 承担。

## 10. 浏览器启动检查补充（2026-04）
- React Router 必须启用已验证的 `future.v7_startTransition`，避免开发期控制台长期提示并让路由切换更接近后续版本行为。
- 受保护路由守卫必须先消费 `AuthProvider` 的 `loading/authenticated/anonymous` 状态，再决定渲染、重定向或角色回退，避免首屏认证异步加载导致子路由丢失。
- 管理端、问答页与登录页的实际启动检查应覆盖控制台错误、页面级横向溢出、四态展示和直达路由可用性。
