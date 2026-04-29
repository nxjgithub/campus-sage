# CampusSage（CSage）

CampusSage 是一个面向高校场景的证据驱动知识库问答系统。系统通过文档入库、向量检索、大模型生成和引用展示，把分散在教务通知、规章制度、办事指南、奖助学金说明等材料中的信息组织成可追溯的问答服务。

项目核心原则是：回答必须基于证据，引用必须可定位，证据不足必须拒答。

## 核心能力

- 知识库管理：创建知识库、配置 TopK、阈值、重排和上下文预算。
- 文档入库：支持 `PDF/DOCX/HTML/Markdown/TXT` 上传，完成解析、切分、Embedding 和 Qdrant 写入。
- 证据问答：同步问答与 SSE 流式问答均返回答案、引用、拒答信息、下一步建议和 `request_id`。
- 引用溯源：每条引用包含 `doc_name`、页码或章节路径、原文片段、文档来源链接等信息。
- 拒答策略：基于分数阈值、关键词覆盖率、最小上下文长度和生成后兜底判定，避免无证据编造。
- 多轮会话：支持会话列表、历史消息、重命名、删除、重新生成、编辑后重发和多轮追问检索改写。
- 会话记忆：最近版本新增 `conversation_memory`，服务重启后仍可用于多轮 query rewrite；记忆摘要只辅助检索，不作为回答证据。
- 评测与监控：支持 Recall@K、MRR、延迟统计、队列监控、运行时诊断和 RAG 健康指标。
- 前端工作台：React 用户端问答页和管理端工作台已落地，覆盖知识库、文档、用户、评测和监控页面。

## 技术栈

- 后端：FastAPI、Pydantic、RQ、Redis
- 数据库：MySQL（默认）、SQLite（兼容）
- 向量库：Qdrant（默认）、内存向量库（本地兜底）
- 模型服务：OpenAI 兼容 Embedding、vLLM / DeepSeek 等 OpenAI 兼容生成接口
- 前端：React、TypeScript、Vite、Ant Design、TanStack Query
- 测试与质量：pytest、ruff、Vitest、ESLint、TypeScript

## 仓库结构

```text
app/                 后端应用代码
  api/               API 路由层
  core/              配置、日志、错误与通用工具
  db/                数据模型、仓库层和迁移
  ingest/            文档解析、切分、Embedding 与入库
  rag/               检索、上下文构造、生成、引用与拒答
  eval/              离线评测
tests/               后端测试
frontend/            React 前端工程
docs/                后端与项目规范文档
docs/frontend/       前端规范文档
scripts/             本地脚本、评测脚本、演示语料导入脚本
data/                本地运行数据目录
docker-compose.yml   MySQL、Qdrant、Redis、TEI、API、Worker 编排
```

## 本地快速启动

以下命令以 Windows PowerShell 为例。所有 Python 命令必须使用仓库本地 `.venv`，禁止使用系统解释器或 `pip --user`。

### 1. 准备后端环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

确认解释器路径位于仓库内：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
```

### 2. 准备配置

```powershell
Copy-Item .env.example .env
```

按本地情况修改 `.env`。本地演示常用配置包括：

```env
DATABASE_URL=mysql+pymysql://csage:csage123@127.0.0.1:3307/csage?charset=utf8mb4
VECTOR_BACKEND=qdrant
QDRANT_URL=http://127.0.0.1:6333
REDIS_URL=redis://127.0.0.1:6379/0
INGEST_QUEUE_ENABLED=true
VLLM_ENABLED=false
```

如需接入 DeepSeek 或其他 OpenAI 兼容生成服务：

```env
VLLM_ENABLED=true
VLLM_BASE_URL=https://api.deepseek.com/v1
VLLM_MODEL_NAME=deepseek-chat
VLLM_API_KEY=your_api_key
```

`.env` 属于本地机密配置，不得提交。

### 3. 启动依赖服务

```powershell
docker compose up -d mysql qdrant redis
```

如需使用本地 TEI Embedding 服务：

```powershell
docker compose up -d mysql qdrant redis tei
```

### 4. 启动后端 API 与 Worker

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

另开一个 PowerShell 启动入库 Worker：

```powershell
.\.venv\Scripts\python.exe -m app.ingest.worker_runner --queue ingest
```

后端 Swagger 地址：

```text
http://127.0.0.1:8000/docs
```

首次使用可创建管理员账号：

```powershell
.\.venv\Scripts\python.exe scripts/create_admin.py --email admin@example.com --password Admin1234
```

### 5. 启动前端

```powershell
cd frontend
pnpm install
pnpm dev -- --host 127.0.0.1 --port 4174
```

前端入口：

```text
http://127.0.0.1:4174/login
```

## Docker Compose 启动

如果希望用容器统一启动 API、Worker 和依赖服务：

```powershell
Copy-Item .env.example .env
docker compose up -d api worker mysql qdrant redis
docker compose ps
```

查看日志：

```powershell
docker compose logs -f api
docker compose logs -f worker
```

停止服务：

```powershell
docker compose down
```

## 演示闭环

建议答辩或验收时按以下流程演示：

1. 登录管理端。
2. 创建知识库并配置检索参数。
3. 上传校园制度、通知或办事指南文档。
4. 查看入库任务状态，确认任务成功。
5. 进入问答页，选择知识库并提问。
6. 展示流式回答、引用弹窗和可定位证据。
7. 连续追问，展示多轮检索改写和会话记忆能力。
8. 提出知识库外问题，展示 `refusal=true` 与下一步建议。
9. 查看会话历史，演示重新生成、编辑后重发和反馈。

也可以导入示例校园语料：

```powershell
.\.venv\Scripts\python.exe scripts/bootstrap_demo_academic_kb.py
```

配套评测集：

```text
docs/examples/eval_set_academic_affairs_demo_md.json
```

## 质量门禁

后端改动后执行：

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

评测相关改动后追加：

```powershell
.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id <kb_id> --eval-file <eval_json> --topk 5
```

前端改动后执行：

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

如果 Qdrant、Redis 或外部模型服务不可用，对应集成测试或联调步骤可能无法完成，需要在提交或交付说明中明确标注。

## 关键契约

- RAG 回答必须包含结构化 `citations`，不得返回无证据答案。
- `refusal=true` 是正常业务结果，前端不得按接口失败处理。
- 引用展示至少包含 `doc_name + page/section_path + snippet`。
- SSE 事件必须保持同一 `request_id`，并尽量以 `done` 事件收敛状态。
- 会话记忆和 query rewrite 只能用于检索补全，不能作为回答证据。
- 所有错误响应统一为 `error + request_id` 结构。
- 影响接口、契约或页面行为的改动必须同步更新文档。

## 常用文档

- [项目总说明](docs/PROJECT_GUIDE.md)
- [项目概览](docs/PROJECT_OVERVIEW.md)
- [本地开发指南](docs/LOCAL_DEV.md)
- [API 规范](docs/API_SPEC.md)
- [RAG 证据契约](docs/RAG_CONTRACT.md)
- [配置说明](docs/CONFIG.md)
- [数据模型](docs/DATA_MODEL.md)
- [演示 SOP](docs/DEMO_SOP.md)
- [前端总览](docs/frontend/FRONTEND_OVERVIEW.md)
- [前端接口契约](docs/frontend/API_CONTRACT.md)

## 最近版本重点

最近一次提交：`a6ab7bb feat(db): 新增会话记忆功能支持多轮检索改写`。

该版本围绕多轮问答增强了后端数据层、RAG 服务、对话策略、LLM 客户端、前端问答页和相关测试。核心变化是新增 `conversation_memory` 持久化轻量会话记忆，服务端可在连续追问时维护主题锚点、近期追问和槽位摘要，用于检索 query rewrite；这些摘要不会替代知识库证据，也不会进入引用列表。

## 安全说明

- 不提交 `.env`、日志、模型权重、大体积数据和 IDE 文件。
- 生产环境必须替换 `JWT_SECRET_KEY`，且长度不少于 32 字符。
- 文档 payload 和日志不得直接记录敏感信息。
- Python 依赖只安装到仓库本地 `.venv`，禁止用户级安装。
