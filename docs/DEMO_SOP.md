# DEMO_SOP.md - 真实业务联调与答辩演示流程

本文档用于统一 CampusSage 的联调演示口径，覆盖多轮对话、意图识别、流式输出、拒答与评测闭环。

## 1. 演示目标
- 证明系统能完成“可检索、可引用、可拒答、可追踪”的真实问答流程。
- 证明多轮对话下的策略有效：模糊提问先澄清，补充后可继续回答。
- 证明时效敏感问题有风险提示，不会把旧制度当成最新制度。
- 证明服务可观测：通过 `request_id` 与监控指标快速定位问题。

## 2. 前置条件
- 后端已启动（示例：`http://127.0.0.1:8010`）。
- 使用本地 `.venv` 执行 Python 命令。
- 管理员账号可用；如不可用，允许脚本自动创建。

推荐先做一次端到端冒烟：

```powershell
.\.venv\Scripts\python.exe scripts/run_api_smoke.py --base-url http://127.0.0.1:8010 --create-admin-if-missing
```

## 3. 真实业务场景清单（建议至少覆盖）
- 场景 A：明确政策问答（应返回 `refusal=false` 且有 citations）
- 场景 B：模糊提问澄清（首轮 `refusal=true` + `next_steps`，次轮补充后恢复正常回答）
- 场景 C：时效敏感提问（答案追加时效提示与官方核验建议）
- 场景 D：流式输出（SSE 事件 `start/token/citation/done`）
- 场景 E：证据不足拒答（`refusal=true`，并返回可执行下一步建议）
- 场景 F：消息再生与反馈闭环（`regenerate + feedback`）

## 4. 标准演示步骤
1. 登录管理端并新建知识库。
2. 上传 1~2 份制度文档，等待入库任务完成。
3. 发送明确业务问题，展示答案中的引用定位信息。
4. 发送模糊问题（如“这个怎么办”），展示澄清型拒答。
5. 在同一会话补充上下文，展示多轮恢复回答。
6. 提问“最新/当前”类问题，展示时效提示与官方核验指引。
7. 使用流式问答接口展示 token 级输出与 done 事件。
8. 对回答执行再生、提交反馈，展示会话可追溯性。
9. 打开 `/api/v1/monitor/runtime`，展示 `rag_metrics` 运行时指标。

## 5. 联调验收口径
- 正常回答必须有可定位引用：`doc_name + page/section_path + snippet`
- 拒答必须是业务正常态（HTTP 200 + `refusal=true`），不能伪造答案
- 流式输出必须可完整收敛到 `done` 事件
- 前端或接口报错必须可追踪 `request_id`
- 时效问题必须有核验提示，不得误导为“最新结论”

## 6. 回归执行建议（每周）
1. 执行 smoke：
```powershell
.\.venv\Scripts\python.exe scripts/run_api_smoke.py --base-url http://127.0.0.1:8010 --create-admin-if-missing
```
2. 执行周回归聚合脚本（smoke + eval）：
```powershell
.\.venv\Scripts\python.exe scripts/run_weekly_regression.py --base-url http://127.0.0.1:8010 --kb-id <kb_id> --eval-file <eval_json> --topk 5
```
3. 归档输出报告：`data/weekly_regression_<run_id>.json`

## 7. 常见问题定位
- `VECTOR_SEARCH_FAILED`：向量后端不可用或配置错误。
- `EMBEDDING_FAILED`：Embedding 服务不可达或模型参数不一致。
- `RAG_MODEL_FAILED`：生成模型不可达、鉴权失败或超时。
- `refusal=true` 但用户认为应可回答：优先检查文档是否入库成功、问题是否缺少业务约束、阈值是否过高。
- 流式中断：检查网络代理、超时设置、以及 run 是否被取消。
