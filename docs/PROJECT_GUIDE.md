# PROJECT_GUIDE.md — CampusSage 项目总说明（后端 + 前端）

## 1. 文档定位
本文件是项目总入口，用于统一指引开发者与 AI Agent 快速理解：
- 项目目标
- 模块边界
- 执行命令
- 文档索引
- 全局完成标准

如果出现规范冲突，以 `AGENTS.md` 约束优先。


## 2. 项目目标与演示闭环
CampusSage 是面向高校场景的证据驱动问答系统（RAG），核心目标是：
- 文档可入库（解析、切分、向量化、写入）
- 问答可追溯（答案必须可关联证据引用）
- 证据不足可拒答（不胡编）
- 行为可回放（会话、反馈、任务日志）

答辩演示闭环建议固定为：
1. 创建知识库
2. 上传文档并触发入库
3. 查看入库任务状态
4. 发起问答并展示引用
5. 触发拒答场景并展示建议
6. 查看会话历史并提交反馈

## 2.1 最新能力快照（已落地）
- 真实 Embedding 已支持 OpenAI 兼容 HTTP 接入，并可通过配置开关切换后端。
- 向量库默认后端已切换为 Qdrant，写入前执行 payload 契约校验。
- 问答上下文已附证据编号，vLLM 提示词要求强制引用编号；缺引用时服务层自动补全。
- 拒答策略已强化，增加关键词覆盖率阈值与最小上下文长度约束。
- chunk 元数据增加页内标题启发式抽取，snippet 清洗稳定性提升。
- `app/eval/` 评测模块已落地，支持 Recall@K、MRR、延迟统计。
- 队列监控已增强：Redis 不可用统一错误、失败告警阈值、死信裁剪。
- `.env.example` 与核心文档已同步新配置。
- 用户管理已落地：JWT 登录/刷新、RBAC 权限、知识库访问控制与管理员脚本。


## 3. 仓库结构总览
- `app/`：后端应用
- `tests/`：后端测试
- `docs/`：全局文档
- `docs/frontend/`：前端规范文档
- `frontend/`：前端工程目录（后续创建）
- `docker-compose.yml`：依赖服务编排


## 4. 文档导航索引
### 4.1 后端核心文档
- `docs/ARCHITECTURE.md`：系统架构与分层
- `docs/API_SPEC.md`：API 契约
- `docs/RAG_CONTRACT.md`：RAG 证据链契约
- `docs/CONVENTIONS.md`：全局工程规范
- `docs/CONFIG.md`：环境变量配置
- `docs/LOCAL_DEV.md`：本地开发流程
- `docs/DATA_MODEL.md`：数据模型设计

### 4.2 前端核心文档
- `docs/frontend/FRONTEND_OVERVIEW.md`：前端范围与页面清单
- `docs/frontend/ARCHITECTURE.md`：前端分层与技术栈
- `docs/frontend/API_CONTRACT.md`：前端接口映射
- `docs/frontend/STATE_AND_INTERACTION.md`：状态机与交互规范
- `docs/frontend/UI_RULES.md`：视觉与样式规范
- `docs/frontend/ERROR_HANDLING.md`：错误处理规范
- `docs/frontend/TEST_STRATEGY.md`：测试与门禁
- `docs/frontend/AI_WORKFLOW.md`：AI 协作工作流


## 5. 开发命令参考
### 5.1 后端
- 安装依赖：`pip install -r requirements.txt`
- 启动依赖：`docker compose up -d`
- 启动 API：`uvicorn app.main:app --reload`
- 代码检查：`ruff check .`
- 单元测试：`pytest -q`
- 运行评测：`python scripts/run_eval.py --kb-id <kb_id> --eval-file <eval_json> --topk 5`

说明：
- 若未启动 Qdrant/Redis，相关集成测试可能被跳过或返回依赖不可用错误，这属于可预期行为。
- 所有 Python 命令默认在 Conda 环境 `campus-sage` 执行；禁止 `pip --user` 用户级安装。

### 5.2 前端（工程创建后）
- 安装依赖：`pnpm install`
- 本地开发：`pnpm dev`
- 代码检查：`pnpm lint`
- 类型检查：`pnpm typecheck`
- 测试：`pnpm test`
- 打包：`pnpm build`


## 6. 全局 Definition of Done（DoD）
任意任务完成时，必须满足：
1. 仅修改与任务相关文件，改动可解释。
2. 对应静态检查与测试通过（后端/前端按改动范围执行）。
3. 错误场景有明确反馈（后端错误码 + 前端可见提示）。
4. 影响契约或行为时，文档已同步更新。
5. 涉及 RAG 时，引用与拒答行为符合契约文档。


## 7. AI 协作建议流程
1. 先读文档，再改代码。
2. 一次只完成一个可验收子任务。
3. 完成后执行检查命令。
4. 输出变更说明、验证结果、剩余风险。


## 8. 当前阶段建议
- 后端已具备主流程能力，建议优先推进前端工程落地。
- 前端实现时严格按 `docs/frontend/` 文档执行，避免与后端接口错位。
- 每周固定一次文档一致性检查，防止“代码领先文档”。
