# AGENTS.md — 给 Codex / AI Agent 的仓库级工作约束（必须遵守）

本项目：CampusSage（CSage）— Evidence-grounded University Knowledge Assistant（RAG）
技术栈：FastAPI + VectorDB(Qdrant/pgvector) + vLLM，Python 为主。

> 目标：让 AI Agent 产出的代码“能跑、可测、可维护、可追溯”，并且适合毕业设计答辩。


## 0. 最高优先级硬约束（违反即视为失败）
1) **所有源码/配置/文档必须 UTF-8 编码**（`.py/.md/.yml/.toml/.json` 等）。
2) **注释与 Docstring 必须使用中文**（解释“为什么这么做/边界条件/异常含义”）。
3) **命名必须使用英文**（模块/函数/类/变量），仅注释中文。
4) **统一换行符 LF**（Windows 本地可 CRLF，但提交时必须是 LF）。
5) **严禁提交 IDE 文件与本地机密**：`.idea/`、`.env`、模型权重、大体积数据集、日志。
6) **任何 RAG 回答必须有证据引用**；证据不足必须拒答/提示，不允许“编”。


## 1. 仓库结构（模块边界要清晰）
推荐结构（按此创建/维护）：
- `app/`：后端应用代码
    - `app/main.py`：FastAPI 入口
    - `app/api/`：路由层（只做入参/出参、依赖注入、调用 service，严禁写复杂逻辑）
    - `app/core/`：配置、日志、异常、通用工具
    - `app/db/`：数据库模型与数据访问（Repository/DAO）
    - `app/ingest/`：入库流水线（解析→chunk→embedding→写向量库）
    - `app/rag/`：问答流水线（检索→上下文→vLLM→引用/拒答）
    - `app/eval/`：离线评测（Recall@K/MRR/延迟统计）
- `tests/`：pytest 测试（`test_*.py`）
- `docs/`：设计与规范（必须保持更新）
- `scripts/`：一次性脚本（导入数据/跑评测等）
- `docker/` & `docker-compose.yml`：依赖服务与部署文件

> 说明：如果当前仓库还没有这些目录，AI Agent 可以按任务需要逐步创建，但必须保持上述边界一致。


## 2. 开发与验证命令（每次任务都必须跑）
在工具链落地前，默认使用以下命令（若后续引入新工具，必须同步更新本节与 README）：

- 代码风格/静态检查：`ruff check .`
- 单元测试：`pytest -q`
- 启动依赖（如已提供）：`docker compose up -d`
- 启动 API：`uvicorn app.main:app --reload`

**Definition of Done（任何任务的完成标准）**
1) 仅修改与任务相关的文件，改动范围可解释；
2) `ruff check .` 通过；
3) `pytest -q` 通过（新增/改动的行为必须有测试）；
4) API 行为有明确错误响应（HTTP 状态码 + 错误码 + 中文错误信息）；
5) 如果影响 RAG：引用字段与格式必须符合 `docs/RAG_CONTRACT.md`。


## 3. 编码规范（AI Agent 必须遵循）
### 3.1 写法与分层
- 路由层（`app/api/`）必须薄：只做参数校验、权限/依赖注入、调用 service、返回响应。
- 业务逻辑在 `app/ingest/`、`app/rag/`、`app/eval/`。
- IO（网络/文件/数据库/向量库）必须显式出现在 service 层，不要隐藏副作用。
- 禁止“巨石函数”：单函数建议 ≤ 50 行，超出必须拆分并补中文注释说明边界。

### 3.2 类型与数据结构
- 公共函数与 service 方法必须写类型标注。
- 请求/响应必须使用 Pydantic Model，并写中文字段说明（Field 描述）。
- 禁止随意返回 `dict`；统一返回明确的 Response Model。

### 3.3 错误处理（统一格式）
- 业务异常必须带 `code`（枚举化），并由统一异常处理中间件转为 HTTP 响应。
- 错误响应建议结构：
  ```json
  {
    "error": {
      "code": "INGEST_PARSE_FAILED",
      "message": "PDF解析失败：未提取到有效文本",
      "detail": {"doc_id": "..."}
    },
    "request_id": "..."
  }
### 3.4 日志与可观测性
- 必须结构化记录关键字段：
- 入库：doc_id, kb_id, chunk_count, embed_count, upsert_count, total_ms
- 问答：kb_id, topk, threshold, rerank, retrieve_ms, generate_ms, total_ms, hit_docs, hit_chunks
- 禁止把敏感信息直接打日志（必要时脱敏）。

## 4. RAG 专属硬约束（可信度底线）
1. 证据不足必须拒答：当检索分数低/证据覆盖不足时，返回 refusal=true，并给出下一步建议。
2. 引用必须可定位：每条引用至少包含 doc_name + page/section + snippet（具体字段以契约为准）。
3. chunk metadata 必须完整：写入向量库时必须携带 docs/RAG_CONTRACT.md 中的必需字段。
4. 上下文拼接必须有 token 预算与去重逻辑，避免爆长导致输出不稳定。

## 5. Git 与提交规范
- 禁止提交：.idea/、.env、__pycache__/、.venv/、日志、权重、大文件数据集。
- 提交信息建议使用 Conventional Commits：
- feat: ... fix: ... chore: ... docs: ... test: ...
- 每次提交前必须确保：ruff + pytest 均通过。

## 6. 文档同步要求
任何会影响接口/契约/行为的变更，必须同步更新：
- docs/API_SPEC.md（接口与 JSON 示例）
- docs/RAG_CONTRACT.md（chunk schema / 引用格式 / 拒答规则）
- docs/CONVENTIONS.md（全局规范，如工具链变更）
