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


## 3. 安装依赖
依赖以你的 `pyproject.toml` / `requirements.txt` 为准。

方案一（requirements）：
```powershell
pip install -U pip
pip install -r requirements.txt
```

方案二（pyproject）：
```powershell
pip install -e .
```

补充：PDF 解析依赖 `pypdf`，若解析失败请确认已安装：
```powershell
pip install pypdf
```

## 3.1 重要提示：避免 pip 安装到用户目录（导致 PyCharm 无法识别）
有些环境的 pip 被配置为默认 `--user`，会把依赖装到：
`C:\Users\用户名\AppData\Roaming\Python\Python312\site-packages`
而不是 conda 环境目录，导致 PyCharm 报“未解析的引用”，或者运行时混用包路径。

**建议做法（强制）**：
```powershell
conda activate campus-sage
python -m pip config set global.user false
python -m pip install -r requirements.txt
```

**核对路径**（必须确保在 conda 环境内）：
```powershell
python -c "import fastapi, uvicorn; print(fastapi.__file__); print(uvicorn.__file__)"
```
期望输出路径类似：
`D:\Anaconda3\envs\campus-sage\Lib\site-packages\...`

如果发现依赖装到了用户目录，先卸载再重装：
```powershell
python -m pip uninstall -y fastapi uvicorn
python -m pip install --no-user -r requirements.txt
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
3) 启动 RQ Worker：
```powershell
python -m rq worker ingest
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
- Windows 换行符：仓库要求 LF，提交前避免把配置文件转为 CRLF
- `.env` 不要提交：必须被 `.gitignore` 忽略
