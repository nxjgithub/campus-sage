# RAG_MAIN_EVAL_V15.md — CampusSage RAG 主线评测集 V15

本文档说明论文第五章建议使用的新评测集：

- 生成脚本：`scripts/build_rag_main_eval_v15.py`
- 输出文件：`docs/examples/eval_set_rag_main_v15.json`
- 基础语料：`docs/examples/official_formal_corpus_v11_manifest.json`
- 原始文件目录：`data/正式文件`

## 1. 重构目标

V11 评测集主要围绕正式文件扩展实验构建，其中不少问题直接包含完整文件名，适合验证文档级召回，但容易让 BM25/Hybrid 对照实验成为论文主线。

V15 评测集将实验目标重新收敛到 CampusSage 的正式 RAG 链路：

1. 向量召回是否能把正确证据纳入候选集合；
2. 重排是否能把正确证据排到更靠前位置；
3. 引用是否具备 `doc_name + page/section + snippet` 的可核验条件；
4. 拒答策略是否能识别知识库外问题和信息不足问题。

## 2. 数据集构成

| 类型 | 数量 | 用途 |
| --- | ---: | --- |
| `semantic_topic` | 45 | 不直接给完整文件名，考察语义召回能力 |
| `detail_evidence` | 45 | 询问材料、时间、流程、条件等细粒度证据 |
| `hard_similar` | 20 | 构造相似主题干扰，重点考察重排收益 |
| `out_of_scope` | 25 | 知识库外问题，考察拒答阈值与边界控制 |
| `clarification` | 15 | 信息不足问题，考察澄清型拒答 |
| 合计 | 150 | 其中知识库内 110 条，知识库外或需澄清 40 条 |

## 3. 字段说明

评测集保留现有离线脚本兼容字段：

- `question`：用户问题；
- `expected`：期望命中的文档主题或拒答说明；
- `gold_doc_name`：标准文档名，知识库外或澄清型问题为 `null`；
- `gold_doc_id`：预留字段，本地实验可为 `null`；
- `gold_page_start` / `gold_page_end`：预留页码字段；
- `question_type`：问题类型；
- `source`：样本来源。

V15 额外增加以下分析字段：

- `answerable`：当前知识库证据是否足够直接回答；
- `evaluation_focus`：样本主要统计维度，如 `vector_recall`、`rerank`、`citation`、`refusal`；
- `expected_citation_required`：是否要求返回引用；
- `expected_refusal_reason`：拒答样本期望原因；
- `gold_evidence_hint`：人工证据提示，仅用于论文分析和人工复核，不应作为模型输入。

## 4. 推荐实验

第五章正文建议围绕以下实验组织：

1. TopK 对向量召回 Recall@K 与 MRR 的影响；
2. 向量召回与“向量召回 + 重排”的消融对比；
3. `candidate_topk` 对重排收益和延迟的影响；
4. 引用完整性与证据可答性统计；
5. 拒答阈值对知识库外拒答率和知识库内误拒率的影响；
6. 相似文件干扰难例分析。

BM25/Hybrid 可以作为补充实验或后续优化方向，不建议作为第五章主线。

## 5. 复现命令

重新生成数据集：

```powershell
.\.venv\Scripts\python.exe scripts\build_rag_main_eval_v15.py
```

运行 TopK、重排消融、候选规模和拒答阈值实验，并生成论文图表：

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_main_v15_experiments.py
```

默认输出目录：

- `outputs/eval_rag_main_v15/rag_main_v15_summary.json`
- `outputs/eval_rag_main_v15/rag_main_v15_report.md`
- `outputs/eval_rag_main_v15/figures/fig_5_2_topk_curve.png`
- `outputs/eval_rag_main_v15/figures/fig_5_3_rerank_ablation.png`
- `outputs/eval_rag_main_v15/figures/fig_5_4_candidate_topk_curve.png`
- `outputs/eval_rag_main_v15/figures/fig_5_5_threshold_curve.png`

运行前必须使用仓库本地虚拟环境 `.venv`，不得退化为系统 Python。

生成后可用以下命令检查脚本风格：

```powershell
.\.venv\Scripts\python.exe -m ruff check scripts\build_rag_main_eval_v15.py scripts\run_rag_main_v15_experiments.py
```
