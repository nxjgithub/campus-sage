# LOCAL_DEV.md — 本地开发指南（Windows + PyCharm + Conda）

本文档用于指导开发者在本地快速启动 CSage。所有命令示例以 PowerShell 为主。


## 1. 环境要求
- Windows 10/11
- Python 3.10+（与当前依赖统一）
- Conda
- Docker Desktop（用于启动 Qdrant 等依赖）
- PyCharm（建议开启 Ruff/pytest 集成）


## 2. 创建并激活 Conda 环境
```powershell
conda create -n campus-sage python=3.12 -y
conda activate campus-sage
```

执行前建议核对当前解释器（必须指向 `campus-sage`）：
```powershell
python -c "import sys; print(sys.executable)"
```


## 3. 安装依赖
依赖以你的 `pyproject.toml` / `requirements.txt` 为准。

方案一（requirements）：
```powershell
python -m pip install -U pip
python -m pip install -r requirements.txt
```

方案二（pyproject）：
```powershell
python -m pip install -e .
```

补充：PDF 解析依赖 `pypdf`，若解析失败请确认已安装：
```powershell
python -m pip install pypdf
```

## 3.1 重要提示：禁止 pip 安装到用户目录（强制）
有些环境的 pip 被配置为默认 `--user`，会把依赖装到：
`C:\Users\用户名\AppData\Roaming\Python\Python312\site-packages`
而不是 conda 环境目录，导致 PyCharm 报“未解析的引用”，或者运行时混用包路径。

**建议做法（强制）**：
```powershell
conda activate campus-sage
python -m pip config set global.user false
python -m pip install -r requirements.txt
```

**禁止行为（强制）**：
- 禁止执行 `pip install --user ...`
- 禁止让 Codex / 其他 AI 工具安装到 `C:\Users\用户名\AppData\Roaming\Python\...`
- 环境异常时必须先修复 Conda 环境，不得以用户级安装“临时通过”

**核对路径**（必须确保在 conda 环境内）：
```powershell
python -c "import fastapi, uvicorn; print(fastapi.__file__); print(uvicorn.__file__)"
```
期望输出路径类似：
`D:\Anaconda3\envs\campus-sage\Lib\site-packages\...`

**强制隔离 user-site（推荐立即执行）**：
```powershell
conda activate campus-sage
conda env config vars set PYTHONNOUSERSITE=1
conda deactivate
conda activate campus-sage
```
可用下面命令确认 `rq/redis` 已从 conda 环境加载：
```powershell
python -c "import rq, redis; print(rq.__file__); print(redis.__file__)"
```
期望输出路径均位于：
`D:\Anaconda3\envs\campus-sage\Lib\site-packages\...`

如果发现依赖装到了用户目录，先卸载再重装：
```powershell
python -m pip uninstall -y fastapi uvicorn
python -m pip install --no-user -r requirements.txt
```

如需清理用户目录中的历史污染包，可按需执行：
```powershell
python -m pip uninstall -y fastapi starlette rq rq-dashboard
```

## 3.2 依赖冲突提示的处理方式
如果安装时出现类似：
`python-docx/python-pptx/sqlalchemy` 依赖 `lxml/Pillow/greenlet` 未安装的警告，
说明环境里存在无关包残留。当前项目代码不依赖这些包，建议直接卸载以保持环境干净：

```powershell
python -m pip uninstall -y python-docx python-pptx sqlalchemy
python -m pip check
```
如未来确实需要这些库，再按需安装缺失依赖即可。


## 4. 配置环境变量
1. 复制 `.env.example` 为 `.env`
2. 按本地情况修改配置（Qdrant、vLLM 地址等）
3. `.env` 不要提交，必须被 `.gitignore` 忽略


## 5. 启动依赖服务（Qdrant）
```powershell
docker compose up -d
docker compose ps
```

## 5.1 启动入库队列（Redis + RQ）
本项目支持使用 RQ + Redis 执行入库任务。开启方式：

1) 启动 Redis（已在 docker compose 中）
2) 设置环境变量：
```
INGEST_QUEUE_ENABLED=true
REDIS_URL=redis://127.0.0.1:6379/0
INGEST_QUEUE_NAME=ingest
```
3) 启动 RQ Worker（跨平台推荐命令，已内置 Windows 兼容超时机制）：
```powershell
python -m app.ingest.worker_runner --queue ingest
```

如需执行一次后退出（排障常用）：
```powershell
python -m app.ingest.worker_runner --queue ingest --burst
```

## 5.2 启用队列监控面板（可选）
如果需要查看队列统计信息，可使用内置监控接口：
- `GET /api/v1/monitor/queues`
- `POST /api/v1/monitor/queues/ingest/move-dead`

也可以安装并启动 RQ Dashboard（需安装额外依赖）：
```powershell
pip install rq-dashboard
rq-dashboard -b 0.0.0.0:9181 -u redis://127.0.0.1:6379/0
```

或直接挂载到 API 服务（需要设置环境变量）：
```
INGEST_QUEUE_DASHBOARD_ENABLED=true
```
启动服务后访问：
`http://127.0.0.1:8000/rq-dashboard`


## 6. 启动 FastAPI
```powershell
uvicorn app.main:app --reload
```

打开：
`http://127.0.0.1:8000/docs`（Swagger）

## 6.1 创建管理员账号
首次使用需创建管理员账号：
```powershell
python scripts/create_admin.py --email admin@example.com --password Admin1234
```


## 7. 运行质量门禁
```powershell
ruff check .
pytest -q
```

## 8. 运行评测脚本
评测集 JSON 格式示例：
```json
{
  "name": "教务评测集_v1",
  "items": [
    {"question": "缓考申请流程是什么？", "gold_doc_id": "doc_123", "gold_page_start": 5, "gold_page_end": 6}
  ]
}
```

执行评测：
```powershell
python scripts/run_eval.py --kb-id kb_123 --eval-file .\data\eval_set.json --topk 5
```


## 9. vLLM 启动说明（可选）
- 本机有 GPU：可本机启动 vLLM
- 没有 GPU：可用远端 vLLM，将 `VLLM_BASE_URL` 指向远端

注意：MVP 阶段可先让 ask 返回固定 mock（仅用于接口联调），正式功能必须接入真实 vLLM。
启用 vLLM 时请设置：
```
VLLM_ENABLED=true
```

## 9.1 方案 1：接入 OpenAI 兼容 Embedding（推荐）
本项目默认已支持 OpenAI 兼容 Embedding 接口，最小配置如下：
```
EMBEDDING_BACKEND=http
EMBEDDING_BASE_URL=http://127.0.0.1:8001/v1
EMBEDDING_API_PATH=/embeddings
EMBEDDING_MODEL_NAME=bge-m3
VECTOR_DIM=1024
```

可选配置：
```
EMBEDDING_API_KEY=your_api_key
EMBEDDING_DIMENSIONS=1024
```

注意：
- `VECTOR_DIM` 必须与实际 Embedding 输出维度一致，否则会触发维度校验失败。
- 若接入的是网关或代理，请确认其兼容 `POST /embeddings` 返回 `data[index, embedding]` 结构。

## 9.2 方案 3 预留埋点：本地 Embedding（按需启用）
当前代码已预留本地后端入口，可通过以下配置切换：
```
EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL_NAME=BAAI/bge-m3
LOCAL_EMBEDDING_DEVICE=cpu
LOCAL_EMBEDDING_NORMALIZE=true
```

说明：
- 该模式依赖 `sentence-transformers`，默认环境未强制安装。
- 未安装依赖时，服务会返回明确错误提示，便于后续按需落地。


## 10. 启用 Qdrant 向量库
1. 安装依赖：
```powershell
pip install qdrant-client
```
2. 设置环境变量：
```
VECTOR_BACKEND=qdrant
QDRANT_URL=http://127.0.0.1:6333
```
3. 重启服务后即可使用 Qdrant 作为向量库后端。


## 11. 常见问题
- Qdrant 端口冲突：检查 6333/6334 是否被占用
- Windows 系统代理导致本地依赖 502：后端已默认对本地 Qdrant/Embedding 请求关闭 `trust_env`，若你刚修改过环境仍失败，请重启 API 与 ingest worker 进程
- 入库报错 `VECTOR_UPSERT_FAILED` 且提示 `field=text`：通常是切分结果里出现纯空白文本块。当前流水线会在 embedding 前自动过滤空白块；若仍复现，请附上 `field/type/value` 详情继续排查。
- Windows 换行符：仓库要求 LF，提交前避免把配置文件转为 CRLF
- `.env` 不要提交：必须被 `.gitignore` 忽略

## 12. 使用 Docker Compose 启动后端与 Worker（推荐）
如果你希望统一用容器启动后端 API 与入库 Worker，可直接使用仓库根目录的 `docker-compose.yml`。

1) 先准备环境变量文件（首次执行）：
```powershell
Copy-Item .env.example .env
```

2) 启动 API + Worker + 依赖服务：
```powershell
docker compose up -d api worker qdrant redis
```

3) 查看服务状态与日志：
```powershell
docker compose ps
docker compose logs -f api
docker compose logs -f worker
```

4) 停止并清理容器（保留卷）：
```powershell
docker compose down
```

说明：
- Compose 中 `api/worker` 已强制使用容器内地址：`QDRANT_URL=http://qdrant:6333`、`REDIS_URL=redis://redis:6379/0`。
- Compose 中 `api/worker` 默认使用容器内 Embedding 地址：`EMBEDDING_BASE_URL=http://tei:80/v1`、`EMBEDDING_API_PATH=/embeddings`，避免容器内误连 `127.0.0.1`。
- 如需自定义容器内 Embedding 地址，可设置 `EMBEDDING_BASE_URL_INTERNAL` 与 `EMBEDDING_API_PATH_INTERNAL`。
- Compose 中 `api/worker` 默认注入 `NO_PROXY=qdrant,tei,redis,localhost,127.0.0.1`，避免本地服务请求被代理劫持。
- 若未配置 Embedding 服务，Compose 默认回退 `EMBEDDING_BACKEND=simple`，便于本地快速跑通。
- 若你需要 HTTP Embedding，请在 `.env` 中显式设置 `EMBEDDING_BACKEND=http` 与可达的 `EMBEDDING_BASE_URL`。
