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
4. 发起问答（同步与流式）并展示引用
5. 演示流式取消（run cancel）
6. 展示会话列表侧栏能力（搜索、分页、重命名、删除）
7. 演示重新生成与编辑后重发（新会话分支）
8. 触发拒答场景并展示建议
9. 查看会话历史并提交反馈

## 2.1 最新能力快照（已落地）
- 真实 Embedding 已支持 OpenAI 兼容 HTTP 接入，并可通过配置开关切换后端。
- 生成模型已支持 OpenAI 兼容 HTTP 接入，可直接切换到 DeepSeek 等外部服务。
- 向量库默认后端已切换为 Qdrant，写入前执行 payload 契约校验。
- 问答上下文已附证据编号，vLLM 提示词要求强制引用编号；缺引用时服务层自动补全。
- 拒答策略已强化，增加关键词覆盖率阈值、最小上下文长度约束与“语义无证据”生成后兜底判定。
- 问答已补充基础多轮策略：支持意图分流、追问 query 补全、信息不足时先澄清再回答。
- 对“最新/当前/今年”等时效型问题，服务层会基于 `published_at` 追加核验提示并引导官方来源。
- 已支持流式问答 SSE：`start/token/citation/refusal/done/error` 事件并携带 request_id。
- 拒答响应已补充结构化 `next_steps`，便于前端渲染“下一步建议”而不只展示纯文本。
- 会话历史中的助手消息也已持久化 `next_steps`，拒答引导可在历史回放中保持一致。
- 文档上传现可选填写 `source_uri`，问答引用与拒答建议会透传官方来源链接，前端可直接跳转核对原文。
- SSE 已增强心跳 `ping` 与断连取消处理，长连接稳定性更高。
- 已支持 chat run 取消接口：`POST /api/v1/chat/runs/{run_id}/cancel`。
- 已支持 chat run 状态查询接口：`GET /api/v1/chat/runs/{run_id}`（断线恢复）。
- 会话能力已补齐：创建、重命名、软删除、关键词检索、游标分页、消息分页。
- 消息能力已补齐：重新生成、编辑后重发（分支会话）。
- Ask 响应新增 `user_message_id` 与 `assistant_created_at`，便于前端稳定渲染。
- 数据层新增 `chat_run`，message 新增 `parent_message_id`、`edited_from_message_id`、`sequence_no`。
- 监控路由统一为 `/api/v1/monitor/*`，去除重复挂载路径。
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
- `frontend/`：前端工程目录
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
- 安装依赖：`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- 启动依赖：`docker compose up -d`
- 容器化启动后端 + Worker：`docker compose up -d api worker qdrant redis`
- 启动 API：`.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- 代码检查：`.\.venv\Scripts\python.exe -m ruff check .`
- 单元测试：`.\.venv\Scripts\python.exe -m pytest -q`
- 运行评测：`.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id <kb_id> --eval-file <eval_json> --topk 5`
- 运行参数对比实验：`.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id <kb_id> --eval-file <eval_json> --compare-topk 3,5,8 --compare-threshold none,0.2,0.3 --compare-rerank false,true`
- 评测前导出知识库文档清单：`.\.venv\Scripts\python.exe scripts/export_eval_inventory.py --kb-id <kb_id>`
- 一键导入示例校园语料：`.\.venv\Scripts\python.exe scripts/bootstrap_demo_academic_kb.py`
- 抓取学校官网公开语料：`.\.venv\Scripts\python.exe scripts/crawl_suse_public_corpus.py`
- 抓取更适合 RAG 的专题语料集：`.\.venv\Scripts\python.exe scripts/crawl_suse_public_corpus.py --profile rag_topics --site-codes jwc,xsc,yjs`
- 清洗公开抓取结果并自动导入知识库：`.\.venv\Scripts\python.exe scripts/bootstrap_suse_public_kb.py --crawl-dir data/crawl/suse_public_<时间戳> --kb-name 四川轻化工大学真实官网语料知识库`
- 样例评测集：`docs/examples/eval_set_academic_affairs_v1.json`
- 示例 Markdown 语料：`docs/examples/academic_demo_corpus/`
- 配套 Markdown 评测集：`docs/examples/eval_set_academic_affairs_demo_md.json`

说明：
- 若未启动 Qdrant/Redis，相关集成测试可能被跳过或返回依赖不可用错误，这属于可预期行为。
- 所有 Python 命令默认使用仓库本地 `.venv` 执行；禁止 `pip --user` 用户级安装。
- 开发环境必须禁用 user-site（`PYTHONNOUSERSITE=1`），避免从 `AppData\Roaming\Python\...` 混入用户级包。

### 5.2 前端
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

## ???????2026-03?
- ??????????????? + ????? + ?????????????
- ?????????????????????????????????????
- ???????????????????????????????????????

## 前端近期更新（2026-03 第二轮）
- 管理端文档页重构为入库工作台，合并上传、当前任务、任务历史与文档操作，降低页面割裂感。
- 评测中心重构为统一工作台，左侧维护评测样本，右侧直接运行与查询结果，不再强调内部运行 ID。
- 问答页补齐剩余提示文案，继续强化“引用可见、证据可查”的交互表达。
- 会话运营页已改为摘要式运营视图，优先显示知识库名称、会话摘要、引用证据与反馈结果，弱化排障信息直出。
- 管理端/用户端布局层已统一重构，侧栏导航、头部说明、门户切换与登录态表达使用同一套门户壳层。
- 管理端知识库页与用户页已开始复用共享工作台组件，后续其余管理页可继续接入，减少布局重复代码。
- `/app/ask` 的特殊布局已改为路由元信息驱动，不再在布局层依赖路径前缀硬编码判断。

## 前端近期更新（2026-03 第三轮）
- 管理端共享工作台组件已继续扩展到文档页与评测页，`kb/users/documents/eval` 四类页面统一复用同一套双栏壳层。
- 共享工作台面板现支持工具条插槽，可承载筛选、密度切换、统计提示等轻量操作区，减少页面级重复布局代码。

## 前端近期更新（2026-03 第四轮）
- 文档上传入口首批支持 `PDF/DOCX/HTML/Markdown/TXT`，管理端文案与上传提示已同步更新。
- 入库 `source_type` 现按真实后缀归一写入，便于后续按来源类型扩展解析与展示。
- 知识库列表已调整列宽策略，名称与说明列优先保留阅读宽度，避免被策略/时间/操作列挤压成竖排显示。
- 知识库页视觉层级已收敛为单一摘要头，分布统计改为页头指标与工具条状态胶囊，整体风格更简洁克制。
- 知识库编辑弹窗已改为轻说明 + 单栏参数布局，统一数字输入宽度，减少局部界面的拥挤感。
- 知识库创建表单已改为“高频字段直出 + 低频参数折叠到高级设置”，首屏更简洁，仍保留完整配置能力。
- 管理端知识库能力现拆分为“列表页 `/admin/kb`”与“创建页 `/admin/kb/create`”，避免创建与治理在同一页面互相干扰。
- 用户端问答页已将顶部大图表收敛为紧凑摘要带，避免摘要模块遮挡消息主视线。

## 前端近期更新（2026-03 第五轮）
- 管理端用户能力现拆分为“列表页 `/admin/users`”与“创建页 `/admin/users/create`”，列表页只处理维护与授权。
- 管理端文档能力现拆分为“管理页 `/admin/documents`”与“上传页 `/admin/documents/upload`”，上传后回到管理页查看任务。
- 管理端评测能力现拆分为“运行页 `/admin/eval`”与“评测集创建页 `/admin/eval/create`”，避免样本录入与结果分析同屏拥挤。
- 拆分后的管理页已补充外层留白和内层面板缓冲边距，修正列表区域左侧贴边拥挤的问题。
- 知识库列表页已同步套用同一套外层留白与内层缓冲边距，修正其仍然贴左边界的问题。
- 知识库列表工具条已拆为两层：第一层保留搜索与“前往创建”，第二层放可见性、统计和密度切换，页面节奏更从容。
- 知识库列表工具条已继续减负：页头承担可见性统计，工具条只保留搜索、创建、筛选和密度控制，整体更简洁克制。
- 知识库页头统计已从四张大卡收敛为横向摘要带，减少大块卡片感，让视觉重心回到列表本身。
- 知识库表格头与分隔线已继续减重，改为低对比浅底表头与轻 hover，整体观感更安静。
- 各管理端创建页已统一补齐“主表单 + 辅助摘要栏”布局，知识库创建、用户创建、文档上传与评测集创建不再只剩单列窄表单悬在空白容器中。

## 前端近期更新（2026-04）
- 前端整体视觉已收敛为轻灰底、白底面板、细边框和低圆角体系，减少装饰性渐变、强阴影和大圆角，便于答辩演示时呈现正式业务系统质感。
- 问答页侧栏品牌断行与管理端侧栏横向滚动问题已修正，聊天工作台继续保持左侧会话、右侧消息与底部输入区的稳定结构。
- 前端错误归一化已修正 Axios 500 误识别问题，缺少统一错误体的服务端异常也会展示中文主提示，并保留错误码与请求 ID 作为排障信息。
- 业务工作台风格已升级：侧栏导航显示模块说明，品牌区改为紧凑产品标识，问答空态提供示例问题和证据链说明，关键会话操作改为文字按钮，整体更贴近主流 SaaS 后台场景。
- 前端高级质感继续增强：问答首屏补充证据约束与拒答策略说明，输入区增加当前知识库上下文，侧栏、表格、按钮和键盘焦点态统一为轻量企业级反馈。

## 后端近期更新（2026-03 数据层）
- SQLite 初始化已重构为显式版本迁移，迁移入口位于 `app/db/migrations.py`，启动时自动执行。
- 迁移历史落表到 `schema_migration`，后续 schema 变更应新增迁移版本，而不是继续在初始化逻辑里堆积兼容补丁。
- 已补充空库初始化、旧库升级、默认角色补种测试，保证数据库层改动具备最小回归保护。

## 后端近期更新（2026-03 配置与观测）
- 上传后缀配置已收口到 `Settings` 层统一归一化，避免文档上传链路各处重复解析。
- 新增 `GET /api/v1/monitor/runtime`，可直接查看当前数据库 schema 版本、关键开关与运行告警。
- 统一错误响应现在会额外写入结构化日志，便于按 `request_id + error_code + path` 检索排障。

## 后端近期更新（2026-03 评测实验）
- `scripts/run_eval.py` 已支持 `threshold` 与 `rerank_enabled` 单次评测参数。
- 新增参数矩阵对比能力，可一次批量比较 `topk / threshold / rerank_enabled` 组合并输出最佳方案摘要。
- 离线评测脚本新增 `gold_doc_name` 匹配能力，便于使用稳定文档名维护样例评测集。
- 第二阶段后续检索优化可直接基于该脚本做可复现实验，而不必手工一组组跑。

## 后端近期更新（2026-03 检索优化）
- `SimpleReranker` 已改为融合正文短语命中、文档标题命中与章节路径命中的启发式重排，适合高校教务类中文问句。
- 重排仍以向量分数作为并列排序兜底，避免仅靠词面命中把明显无关的候选抬到前面。
- 已补充 `tests/test_reranker.py`，覆盖“正文精确命中优先”“标题/章节命中优先”“空问题不改序”三类回归场景。
- 新增 `scripts/export_eval_inventory.py`，可从 Qdrant 直接导出知识库中的文档名、页码范围与章节路径样本，降低离线评测集对齐成本。
- 新增 `scripts/bootstrap_demo_academic_kb.py` 与配套示例语料，可在空环境中快速构建第二阶段参数实验基线。
- 新增 `scripts/crawl_suse_public_corpus.py`，可定向抓取四川轻化工大学公开栏目与附件，生成带 `source_uri` 的本地真实语料清单。
- 新增 `scripts/bootstrap_suse_public_kb.py`，可对公开抓取结果做二次清洗、列表页详情补抓、可入库格式筛选，并自动创建知识库完成批量导入。
- `dialog_policy` 已扩展招生/报考词域（如“招生/报考/网报/复试/分数线/考点”），多轮场景下可减少该类问题被误判为澄清拒答。
- `crawl_suse_public_corpus.py` 已补充标准输出 UTF-8 自适应，降低 Windows 控制台因编码导致的脚本收尾报错风险。

## 联调新增（2026-03）
- 新增 `docs/DEMO_SOP.md`，固化真实业务演示流程与验收口径。
- 新增 `scripts/run_api_smoke.py`，用于接口冒烟联调与 CI 门禁。
- 新增 `scripts/run_weekly_regression.py`，用于每周执行 smoke + eval 并输出统一报告。
