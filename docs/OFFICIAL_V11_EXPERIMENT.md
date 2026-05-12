# CampusSage V11 正式文件扩展实验

本文档记录论文 V11 使用的正式文件实验数据、评测集与复现实验命令。

## 数据来源

- 原始目录：`data/正式文件`
- 可解析文件数：45
- 文件类型：PDF、DOCX
- 解析后文本块数：405
- 解析后总字符数：67789
- 评测集：`docs/examples/eval_set_official_formal_v11.json`
- 语料清单：`docs/examples/official_formal_corpus_v11_manifest.json`
- 输出目录：`outputs/eval_official_formal_v11_fast`

评测集共 100 条问题，其中 90 条为知识库内问题，10 条为知识库外边界问题。每份正式文件至少包含 2 条知识库内问题，用于验证系统在更多真实校园通知和附件中定位标准文档的能力。

## 实验配置

| 配置项 | 值 |
| --- | --- |
| embedding 模型 | `BAAI/bge-small-zh-v1.5` |
| rerank 模型 | `BAAI/bge-reranker-base` |
| embedding 后端 | 本地 `sentence-transformers` |
| rerank 后端 | 本地 `CrossEncoder` |
| chunk_size | 500 |
| chunk_overlap | 100 |
| candidate_topk | 20 |
| final_topk | 5 |

本轮实验原计划使用 Docker TEI 服务，但当前 Docker GPU runtime 无法启动 CUDA 版 TEI 镜像。因此 V11 采用仓库本地 `.venv` 中的 `sentence-transformers` 加载同名 BGE 模型完成实验，仍属于真实 embedding 与真实 cross-encoder 重排实验。

## 复现命令

```powershell
.\.venv\Scripts\python.exe scripts\build_official_experiment_assets.py
```

如本地尚未缓存模型，需要先联网下载模型到仓库缓存目录：

```powershell
$env:HF_HOME='D:\myproject\campus-sage\data\hf_cache'
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-small-zh-v1.5', device='cpu'); CrossEncoder('BAAI/bge-reranker-base', device='cpu')"
```

运行 V11 快速评测：

```powershell
$env:HF_HOME='D:\myproject\campus-sage\data\hf_cache'
.\.venv\Scripts\python.exe scripts\run_official_v11_fast_eval.py --embedding-backend local --rerank-backend local --embedding-batch-size 4
```

生成论文 V11：

```powershell
.\.venv\Scripts\python.exe scripts\create_thesis_v11.py
```

## 核心结果

| TopK | Recall | MRR | Top1 命中 | 命中数/样本 |
| --- | --- | --- | --- | --- |
| 3 | 0.9444 | 0.9389 | 84 | 85/90 |
| 5 | 0.9556 | 0.9411 | 84 | 86/90 |
| 8 | 0.9556 | 0.9411 | 84 | 86/90 |

| 是否重排 | Recall@5 | MRR | Top1 命中 | 命中数/样本 |
| --- | --- | --- | --- | --- |
| 否 | 0.9222 | 0.8381 | 72/90 | 83/90 |
| 是 | 0.9556 | 0.9411 | 84/90 | 86/90 |

该结果说明，在 45 份正式文件、405 个文本块和 100 条评测问题上，`BAAI/bge-reranker-base` 能明显提升标准证据排序质量。
