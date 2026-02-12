# CampusSage Frontend

## 本地启动
1. 安装依赖：`npm install`
2. 启动开发服务：`npm run dev`
3. 访问：`http://127.0.0.1:5173`

## 路由约定
- 登录页：`/login`
- 管理员端：`/admin/*`（需登录且角色含 `admin`）
  - `users` 用户管理
  - `kb` 知识库管理
  - `documents` 文档与入库
  - `eval` 评测中心
  - `monitor` 队列监控
- 用户端：`/app/*`
  - `ask` 支持匿名问答（public 知识库）
  - `conversations` 需登录

## 认证说明
- 前端使用 JWT（access_token + refresh_token）
- 请求自动注入 `Authorization` 与 `X-Request-ID`
- 遇到 401 时自动尝试刷新 token 并重放一次请求
- 刷新失败会清理本地凭证并回到匿名态

## 常用命令
- `npm run typecheck`
- `npm run lint`
- `npm run test`
- `npm run build`

## 类型生成
- `npm run gen:types`
- 默认从 `http://127.0.0.1:8000/openapi.json` 生成
