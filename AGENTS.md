# AGENTS.md — 给 Codex / AI Agent 的仓库级工作约束（必须遵守）

本项目：CampusSage（CSage）— Evidence-grounded University Knowledge Assistant（RAG）  
当前技术栈：FastAPI + VectorDB(Qdrant 默认) + vLLM + OpenAI 兼容 Embedding（后端）+ React 前端规划文档（待实现）

> 目标：让 AI Agent 产出的代码“能跑、可测、可维护、可追溯”，并可用于毕业设计答辩演示。


## 0. 最高优先级硬约束（违反即失败）
1. 所有源码/配置/文档必须 UTF-8 编码（`.py/.md/.yml/.toml/.json/.ts/.tsx/.css`）。
2. 注释与 Docstring 必须使用中文（解释设计原因、边界条件、异常含义）。
3. 命名必须使用英文（模块/函数/类/变量），仅注释中文。
4. 统一换行符 LF（Windows 本地可 CRLF，但提交时必须 LF）。
5. 严禁提交 IDE 文件与本地机密：`.idea/`、`.env`、模型权重、大体积数据、日志。
6. 任何 RAG 回答必须有证据引用；证据不足必须拒答，不允许编造。
7. 修改行为必须同步文档，禁止“代码变了但文档没变”。
8. Python 相关操作（`python/pip/ruff/pytest`）必须在 Conda 虚拟环境 `campus-sage` 中执行，禁止在系统解释器执行。
9. 严禁安装用户级 Python 包（禁止 `pip install --user` 或写入 `AppData\Roaming\Python\...`）；包括 Codex 在内的所有 AI 工具都不得绕过此约束。


## 1. 仓库结构与边界
推荐结构（按此维护）：
- `app/`：后端应用代码
  - `app/main.py`：FastAPI 入口
  - `app/api/`：路由层（仅参数校验、依赖注入、调用 service）
  - `app/core/`：配置、日志、异常、通用工具
  - `app/db/`：数据模型与仓库层
  - `app/ingest/`：入库流水线（解析→chunk→embedding→向量写入）
  - `app/rag/`：问答流水线（检索→上下文→生成→引用/拒答）
  - `app/eval/`：离线评测
- `tests/`：后端 pytest 测试
- `docs/`：设计与规范文档
- `docs/frontend/`：前端规范文档
- `frontend/`：前端工程（后续创建）
- `scripts/`：一次性脚本

约束：
- 后端业务层不得依赖 API 层。
- 前端页面层不得直接裸调接口，必须走统一 API 层。
- 前后端契约以文档为准，不得私自扩展未约定字段。


## 2. 开发与验证命令（按改动范围执行）
后端改动必须执行：
- `ruff check .`
- `pytest -q`
- 评测相关改动附加执行：`python scripts/run_eval.py --kb-id <kb_id> --eval-file <eval_json> --topk 5`

环境约束（强制）：
- 执行以上命令前必须确保已激活 `conda activate campus-sage`（或使用 `conda run -n campus-sage ...`）。
- 若环境不可用，必须先报错说明，不得退化为 `pip --user` 安装依赖。

前端改动（`frontend/` 建立后）必须执行：
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build`

如果环境缺失导致无法执行，必须在结果中明确说明“未执行项、原因、影响范围”。
集成测试说明：
- Qdrant/Redis 依赖不可用时，允许跳过对应集成测试，但必须在结果说明中标注。


## 3. 后端实现规范
### 3.1 分层与写法
- 路由层（`app/api/`）必须薄，不写复杂业务。
- 业务逻辑集中在 `app/ingest`、`app/rag`、`app/eval`。
- IO 副作用必须显式出现在 service 层。
- 避免巨石函数，复杂逻辑必须拆分并加中文注释。

### 3.2 类型与模型
- 公共函数与 service 方法必须有类型标注。
- 请求/响应统一使用 Pydantic Model。
- 禁止对外返回随意 `dict`（除约定的简单删除响应外）。

### 3.3 错误与日志
- 业务异常必须带错误码（枚举化）。
- 错误响应必须统一结构（`error + request_id`）。
- 日志必须结构化，关键字段可检索。
- 禁止直接记录敏感信息，必要时脱敏。
- 队列相关错误必须统一返回可读错误（例如 Redis 不可用），并记录失败原因。


## 4. 前端实现规范（强制）
前端实现必须遵循：
- `docs/frontend/FRONTEND_OVERVIEW.md`
- `docs/frontend/ARCHITECTURE.md`
- `docs/frontend/API_CONTRACT.md`
- `docs/frontend/STATE_AND_INTERACTION.md`
- `docs/frontend/UI_RULES.md`
- `docs/frontend/ERROR_HANDLING.md`
- `docs/frontend/TEST_STRATEGY.md`
- `docs/frontend/AI_WORKFLOW.md`

前端硬约束：
1. 每个页面必须有 `loading/success/empty/error` 四态。
2. `refusal=true` 属于业务正常态，不得按接口失败处理。
3. 引用展示必须包含 `doc_name + (page 或 section_path) + snippet`。
4. 所有错误提示必须可追踪 `request_id`。
5. 样式必须遵循统一视觉规范，不得无约束拼接第三方样式。


## 5. RAG 专属硬约束
1. 证据不足必须拒答（`refusal=true`），并给出下一步建议。
2. 引用必须可定位（文档名 + 页码/章节 + 片段）。
3. 向量 metadata 必须完整，符合 `docs/RAG_CONTRACT.md`。
4. 上下文构造必须有预算与去重，避免超长导致不稳定。
5. vLLM 生成答案必须带证据编号（如 `[1][2]`）；若模型遗漏，服务层必须自动补全引用标记。
6. 拒答策略必须至少包含：分数阈值、关键词覆盖率阈值、最小上下文长度。
7. Qdrant 写入前必须执行 payload 契约校验，不允许缺字段写入。


## 6. Git 与提交规范
- 禁止提交：`.idea/`、`.env`、`__pycache__/`、`.venv/`、日志、权重、大文件数据集。
- 提交信息建议：Conventional Commits
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `test: ...`
  - `chore: ...`
- 提交前必须完成对应检查命令。


## 7. 文档同步规则（强制）
任何影响接口、契约、页面行为的变更，必须同步更新对应文档：
- 后端契约文档：
  - `docs/API_SPEC.md`
  - `docs/RAG_CONTRACT.md`
  - `docs/CONVENTIONS.md`
  - `docs/CONFIG.md`
  - `docs/LOCAL_DEV.md`
- 前端规范文档：
  - `docs/frontend/API_CONTRACT.md`
  - `docs/frontend/STATE_AND_INTERACTION.md`
  - `docs/frontend/ERROR_HANDLING.md`
  - `docs/frontend/UI_RULES.md`
- 总入口文档：
  - `docs/PROJECT_GUIDE.md`


## 8. AI Agent 执行流程（必须遵守）
1. 开始任务先读取相关文档，再动代码。
2. 每次只做一个可验收的小任务。
3. 先实现，再验证，再更新文档。
4. 输出结果必须包含：
   - 修改文件列表
   - 执行过的命令与结果
   - 未执行项及原因
   - 风险与下一步建议


## 9. 禁止行为
- 不允许绕开契约“临时凑合”。
- 不允许无测试修改核心流程。
- 不允许静默吞异常。
- 不允许在未说明的情况下大改目录结构。
- 不允许编造后端不存在的字段或前端行为。
- 不允许使用 `pip --user` 或任何用户级 Python 包安装方式污染宿主环境。
