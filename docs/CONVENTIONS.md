
---
# CONVENTIONS.md — CampusSage 全局工程规范（适用于人类与 AI Agent）

本文档定义本项目的全局约束、编码风格、目录边界、错误与日志规范、测试门禁等。
任何与本文冲突的实现视为“不合格提交”。


## 1. 文件编码与文本规范（强制）
1) **全部文件使用 UTF-8 编码**：源码/文档/配置统一 UTF-8（无 BOM 也可，保持一致）。
2) **注释与 Docstring 使用中文**：解释设计原因、边界条件、异常含义、关键算法步骤。
3) **标识符命名使用英文**：模块/函数/类/变量英文，避免中英混杂带来工具链问题。
4) **换行符统一 LF**：提交到 Git 的文件必须是 LF。
5) **缩进 4 空格**，文件末尾必须有空行。
6) 建议行宽 88（与常见 Python 工具兼容）。

推荐落地文件（如尚未添加，可后续补充）：
- `.editorconfig`：强制 UTF-8 / LF / 缩进
- `.gitattributes`：强制仓库层面的 eol=lf


## 2. 目录边界与分层职责（强制）
### 2.1 路由层（app/api）
- 只做：入参出参校验、依赖注入、权限/鉴权、调用 service、返回响应。
- 禁止：复杂业务流程、跨多组件的 orchestration、直接写 DB/向量库。

### 2.2 业务层（app/ingest、app/rag、app/eval）
- ingest：解析 → 清洗 → chunk → embedding → 向量 upsert → 状态/日志
- rag：检索 →（可选重排）→ 上下文构造 → vLLM 生成 → 引用 → 拒答
- eval：评测集加载 → 指标计算（Recall@K/MRR/延迟）→ 报告导出

### 2.3 核心公共层（app/core）
- Settings（环境变量、默认值、配置校验）
- 日志（统一 logger、结构化字段约定）
- 异常（错误码、业务异常基类、异常处理中间件）
- 通用工具（但禁止堆“杂物”，不相关工具应放 scripts/）

### 2.4 数据访问层（app/db）
- ORM 模型 / Repository / 数据迁移（如 Alembic）
- 禁止在业务层散落 SQL；统一在 db 层封装。
- 会话/消息/反馈必须落库，保证服务重启后可追溯。
- 聊天运行（chat_run）必须落库，记录流式运行状态与取消标记。
- message 表必须支持会话分支追踪字段：`parent_message_id`、`edited_from_message_id`、`sequence_no`。


## 3. 命名规范（强制）
- 文件/函数/变量：`snake_case`
- 类：`CapWords`
- 常量：`UPPER_SNAKE_CASE`
- Pydantic Model：
  - Request：`XxxRequest`
  - Response：`XxxResponse`
  - 内部 DTO：`XxxDTO`
- Endpoint 资源命名使用名词，动作使用 HTTP 方法表达：
  - `POST /kb` 创建
  - `POST /kb/{kb_id}/documents` 上传/入库
  - `POST /kb/{kb_id}/ask` 问答
  - `GET /kb/{kb_id}/documents` 列表
  - `DELETE /documents/{doc_id}` 删除


## 4. 类型标注与数据建模（强制）
1) 业务函数必须写类型标注（尤其是 public 方法）。
2) 不允许“随手 dict”：对外响应必须是 Pydantic Response Model。
3) 不要滥用 `Any`：确实不可避免时必须写中文注释说明原因与风险。
4) 与向量库交互的 chunk metadata 字段必须严格遵循 `docs/RAG_CONTRACT.md`。


## 5. 错误码与异常规范（强制）
### 5.1 错误码枚举化
错误码必须集中定义（建议 `app/core/error_codes.py`），禁止散落字符串。
示例类别：
- INGEST_*：解析、切分、embedding、upsert 失败
- EMBEDDING_*：向量模型调用失败
- VECTOR_*：向量库连接/写入/删除失败
- RAG_*：检索无证据、上下文构造失败、模型调用失败
- AUTH_*：认证/授权/令牌错误
- USER_*：用户管理相关错误
- VALIDATION_*：入参校验失败
- KB_*：知识库相关错误（如唯一性冲突）
- INGEST_JOB_*：入库任务相关错误（如不可重试）
- CONVERSATION_*：会话相关错误
- MESSAGE_*：消息相关错误
- CHAT_RUN_*：流式运行相关错误

### 5.2 统一错误响应格式
建议统一为：
```json
{
  "error": {
    "code": "RAG_NO_EVIDENCE",
    "message": "当前知识库中未找到足够证据，无法给出可靠答案。",
    "detail": {"kb_id": "...", "topk": 5}
  },
  "request_id": "..."
}
```

### 5.3 分层处理原则

业务层抛业务异常（带 code/message/detail）

API 层统一捕获并映射 HTTP 状态码

不要吞异常；若需要降级，必须记录日志并写中文注释说明。

入库任务状态变化需记录 `error_code`（如 `INGEST_CANCELED`），便于机器可读分析。

## 6. 日志与可观测性（强制）
### 6.1 request_id
- 每个请求必须有 request_id（可由中间件生成），贯穿日志与错误响应。
- SSE 场景中，同一请求的所有事件必须携带一致的 `request_id`。

### 6.2 必填日志字段

- 入库：
 - kb_id, doc_id, pages, chunk_count, embed_count, upsert_count
 - parse_ms, chunk_ms, embed_ms, upsert_ms, total_ms
 - job_status（queued/running/succeeded/failed）
- 问答：
 - kb_id, topk, threshold, rerank_enabled
 - retrieve_ms, rerank_ms, context_ms, generate_ms, total_ms
 - hit_docs, hit_chunks, refusal_reason
- 评测：
 - eval_set_id, samples, recall_at_k, mrr, avg_ms, p95_ms
- 错误响应：
 - request_id, method, path, status_code, error_code
 - 允许记录 `detail_keys` 这类结构摘要，禁止把敏感明细原样打入日志

### 6.3 敏感信息
- 禁止将手机号/身份证/学号等敏感数据原样写日志。
- 如必须记录，做脱敏（只保留部分字符）。

## 7. RAG 可信度规范（强制）
1. 证据不足必须拒答：输出 refusal=true，并提供建议（去哪里查/建议关键词）。
2. 引用必须可定位：至少包含文档名、页码/章节、命中片段。
3. 引用字段不可缺失：引用 schema 以 docs/RAG_CONTRACT.md 为准。
4. 上下文构造必须有 token 预算并去重，避免“把所有 chunk 全塞进去”。
5. 流式问答必须有 `start -> ... -> done` 的可收敛事件序列，错误与取消也要落到 `done`。

## 8. 权限与路由一致性（强制）
1. 会话写操作（创建、重命名、删除）必须要求 `conversation.write`。
2. 消息写操作（取消 run、重生成、编辑重发）必须要求 `message.write`。
3. 监控接口统一挂载在 `/api/v1/monitor/*`，禁止额外暴露重复入口。
4. chat run 查询/取消必须校验运行归属（`chat_run.user_id`），禁止仅凭权限操作任意 `run_id`。

## 9. 测试与质量门禁（强制）
1. 每新增一个核心行为必须配测试：
  - 正常路径 1 个
  - 边界/错误路径 1 个（例如：无证据拒答、文档不存在、向量库不可用等）
2. 任何 PR/提交都必须通过：
  - ruff check .
  - pytest -q
3. 关键结构建议做“金样测试（Golden Test）”：
  - 固定输入时，至少保证 response 的字段结构稳定（尤其 citations）。

## 10. 配置与依赖（强制）
1. 配置必须来自环境变量 + Settings（建议 Pydantic Settings）。
2. 必须提供 .env.example（不含密钥）。
3. 禁止硬编码：Qdrant/vLLM 地址、模型名、TopK、阈值、上下文 token 上限等都要可配置。
4. 依赖版本要可复现（pyproject/requirements 固定范围），升级依赖需写变更说明。
5. Python 依赖安装与测试命令必须在仓库本地 `.venv` 内执行，禁止使用系统 Python 混跑。
6. 严禁用户级安装（`pip install --user`）；若环境权限不足，应先修复 `.venv` 或其依赖，而不是回退到用户目录安装。

## 11. Git 与提交规范（强制）
1. 禁止提交：.idea/、.env、.venv/、__pycache__/、日志、权重、大数据文件。
2. 提交信息建议采用 Conventional Commits：
 - feat: ... fix: ... chore: ... docs: ... test: ...
3. 提交前自检：ruff + pytest。
