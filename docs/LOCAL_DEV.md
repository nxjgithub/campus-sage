# LOCAL_DEV.md — 本地开发指南（Windows + PyCharm + .venv）

本文档用于指导开发者在本地快速启动 CSage。所有命令示例以 PowerShell 为主。


## 1. 环境要求
- Windows 10/11
- Python 3.10+（与当前依赖统一）
- Docker Desktop（用于启动 MySQL / Qdrant / Redis / TEI 等依赖）
- PyCharm（建议开启 Ruff/pytest 集成）


## 2. 创建并激活本地 `.venv`
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

执行前建议核对当前解释器（必须指向仓库内 `.venv`）：
```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
```


## 3. 安装依赖
依赖以你的 `pyproject.toml` / `requirements.txt` 为准。

方案一（requirements）：
```powershell
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

方案二（pyproject）：
```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

补充：PDF 解析依赖 `pypdf`，若解析失败请确认已安装：
```powershell
.\.venv\Scripts\python.exe -m pip install pypdf
```

## 3.1 重要提示：禁止 pip 安装到用户目录（强制）
有些环境的 pip 被配置为默认 `--user`，会把依赖装到：
`C:\Users\用户名\AppData\Roaming\Python\Python312\site-packages`
而不是仓库本地 `.venv`，导致 PyCharm 报“未解析的引用”，或者运行时混用包路径。

**建议做法（强制）**：
```powershell
.\.venv\Scripts\python.exe -m pip config set global.user false
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**禁止行为（强制）**：
- 禁止执行 `pip install --user ...`
- 禁止让 Codex / 其他 AI 工具安装到 `C:\Users\用户名\AppData\Roaming\Python\...`
- 环境异常时必须先修复仓库本地 `.venv`，不得以用户级安装“临时通过”

**核对路径**（必须确保在仓库本地 `.venv` 内）：
```powershell
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn; print(fastapi.__file__); print(uvicorn.__file__)"
```
期望输出路径类似：
`D:\myproject\campus-sage\.venv\Lib\site-packages\...`

**强制隔离 user-site（推荐立即执行）**：
```powershell
$env:PYTHONNOUSERSITE="1"
```
可用下面命令确认 `rq/redis` 已从 `.venv` 加载：
```powershell
.\.venv\Scripts\python.exe -c "import rq, redis; print(rq.__file__); print(redis.__file__)"
```
期望输出路径均位于：
`D:\myproject\campus-sage\.venv\Lib\site-packages\...`

如果发现依赖装到了用户目录，先卸载再重装：
```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y fastapi uvicorn
.\.venv\Scripts\python.exe -m pip install --no-user -r requirements.txt
```

如需清理用户目录中的历史污染包，可按需执行：
```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y fastapi starlette rq rq-dashboard
```

## 3.2 依赖冲突提示的处理方式
如果安装时出现类似：
`python-docx/python-pptx/sqlalchemy` 依赖 `lxml/Pillow/greenlet` 未安装的警告，
说明环境里存在无关包残留。当前项目代码不依赖这些包，建议直接卸载以保持环境干净：

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y python-docx python-pptx sqlalchemy
.\.venv\Scripts\python.exe -m pip check
```
如未来确实需要这些库，再按需安装缺失依赖即可。


## 4. 配置环境变量
1. 复制 `.env.example` 为 `.env`
2. 按本地情况修改配置（MySQL、Qdrant、vLLM 地址等）
3. `.env` 不要提交，必须被 `.gitignore` 忽略


## 5. 启动依赖服务（MySQL + Qdrant）
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
.\.venv\Scripts\python.exe -m app.ingest.worker_runner --queue ingest
```

如需执行一次后退出（排障常用）：
```powershell
.\.venv\Scripts\python.exe -m app.ingest.worker_runner --queue ingest --burst
```

## 5.2 启用队列监控面板（可选）
如果需要查看队列统计信息，可使用内置监控接口：
- `GET /api/v1/monitor/queues`
- `POST /api/v1/monitor/queues/ingest/move-dead`

也可以安装并启动 RQ Dashboard（需安装额外依赖）：
```powershell
.\.venv\Scripts\python.exe -m pip install rq-dashboard
.\.venv\Scripts\rq-dashboard.exe -b 0.0.0.0:9181 -u redis://127.0.0.1:6379/0
```

或直接挂载到 API 服务（需要设置环境变量）：
```
INGEST_QUEUE_DASHBOARD_ENABLED=true
```
启动服务后访问：
`http://127.0.0.1:8000/rq-dashboard`


## 6. 启动 FastAPI
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

打开：
`http://127.0.0.1:8000/docs`（Swagger）

## 6.1 创建管理员账号
首次使用需创建管理员账号：
```powershell
.\.venv\Scripts\python.exe scripts/create_admin.py --email admin@example.com --password Admin1234
```


## 7. 运行质量门禁
```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

## 7.1 数据库 schema 排查
- `uvicorn app.main:app --reload` 启动时会自动初始化数据库 schema；SQLite 走增量迁移，MySQL 走空库初始化。
- MySQL 初始化会为每张业务表和每个字段写入中文 `COMMENT`，可在数据库管理工具中直接查看字段含义。
- 若你本地仍保留旧的 `csage.db`，SQLite 启动后应自动生成 `schema_migration` 表并补齐缺失列。
- 可用以下命令快速检查迁移状态：
```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; conn=sqlite3.connect('./data/csage.db'); print(conn.execute('SELECT version, name FROM schema_migration ORDER BY version').fetchall())"
```
- 若你当前使用 MySQL，可改用：
```powershell
docker compose exec mysql mysql -ucsage -pcsage123 -D csage -e "SELECT version, name FROM schema_migration ORDER BY version;"
```
- 若 SQLite 数据库文件已损坏或历史结构异常，优先备份后删除本地 SQLite 文件，再重启服务让系统重建；不要手工跳过迁移记录。
- 若 MySQL schema 已被手工改坏，优先新建空数据库实例重新初始化，不要在半迁移旧库上继续叠补丁。
- 若你怀疑服务实际加载的配置与 `.env` 不一致，可登录后访问 `GET /api/v1/monitor/runtime` 检查当前 schema 版本、上传配置和关键开关。
- 若你计划用 `APP_ENV=prod` 启动演示环境，必须先确认 `JWT_SECRET_KEY` 已替换且长度不少于 32；否则服务会在启动阶段直接报错并拒绝运行。

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
.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id kb_123 --eval-file .\data\eval_set.json --topk 5
```

执行参数对比实验：
```powershell
.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id kb_123 --eval-file .\data\eval_set.json --compare-topk 3,5,8 --compare-threshold none,0.2,0.3 --compare-rerank false,true
```
如需逐题查看“原始命中/阈值后命中/最终排名”，可追加：
```powershell
.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id kb_123 --eval-file .\data\eval_set.json --topk 5 --rerank-enabled --show-items
```
说明：
- `--threshold` 与 `--rerank-enabled` 现在也可用于单次评测。
- `--compare-*` 任一参数出现时，脚本会生成参数矩阵并输出排序后的实验结果。
- `--compare-threshold` 中可使用 `none` 表示不额外做分数阈值过滤。
- `--show-items` 会输出逐题明细，重点字段包括：
  - `raw_rank`：阈值与重排前的原始命中排名
  - `threshold_rank`：分数阈值过滤后的命中排名
  - `rank`：最终截回 `topk` 后的命中排名
  - `top_candidates`：原始检索前几个候选文档及分数
- 评测输出现在还会附带 `diagnostics` 摘要，重点可看：
  - `threshold_filtered_relevant_count`：原始已命中但被阈值过滤掉的题数
  - `rerank_promoted_count`：重排后排名上升的题数
  - `top1_hit_count`：最终命中排在第 1 位的题数
- `run_eval.py` 直接读取本地 `.env` / 环境变量，不会自动继承你已启动 API 进程的运行参数。
- 如果你的 API 是用 `EMBEDDING_BACKEND=simple` 或其他临时覆盖参数跑通的，评测脚本也必须显式传入同样的覆盖参数。
- 若你正在调优启发式重排，可同时关注 `RAG_RERANK_CANDIDATE_MULTIPLIER` 与 `RAG_RERANK_CANDIDATE_CAP`；系统会先放大候选池，再重排后截回最终 `topk`。
- 常见排障：
  - 若报 `Embedding 服务不可用`，先检查当前是否仍在使用 `.env` 里的 `EMBEDDING_BACKEND=http` 与 `EMBEDDING_BASE_URL=http://127.0.0.1:8001/v1`。
  - 若你只是想复现本地 demo 基线，可直接追加 `--embedding-backend simple`。
- 常用覆盖参数：
  - `--embedding-backend http|simple|local`
  - `--embedding-base-url <url>`
  - `--embedding-api-path <path>`
  - `--vector-backend memory|qdrant`
  - `--qdrant-url <url>`
- 仓库已提供可复用样例：`docs/examples/eval_set_academic_affairs_v1.json`
- 若你需要一套可直接导入的校园示例语料，可使用：`docs/examples/academic_demo_corpus/`
- 与示例语料配套的 Markdown 评测集：`docs/examples/eval_set_academic_affairs_demo_md.json`
- 离线脚本除 `gold_doc_id` 外，也支持按 `gold_doc_name` 匹配文档，适合在文档导入后 `doc_id` 不稳定的本地实验场景。
- 若你直接使用 API 创建评测集，仍应以 `gold_doc_id` 为准；`gold_doc_name` 仅用于离线脚本样例与本地实验。

若你还没有对齐好的评测集，可先导出知识库中的文档清单：
```powershell
.\.venv\Scripts\python.exe scripts/export_eval_inventory.py --kb-id kb_123
```
补充说明：
- 该脚本会直接读取 Qdrant payload，输出 `doc_name / doc_id / page_start_min / page_end_max / section_path_examples`。
- 推荐先用导出的文档清单核对 `gold_doc_name` 与页码范围，再运行 `run_eval.py` 做参数实验。

若你想直接搭一套可复现的实验基线，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/bootstrap_demo_academic_kb.py
```
补充说明：
- 该脚本会调用本地 API，登录默认管理员 `admin@example.com / Admin1234`，创建“高校教务示例知识库”并上传 `docs/examples/academic_demo_corpus/` 中的示例文档。
- 导入完成后，可直接配合 `docs/examples/eval_set_academic_affairs_demo_md.json` 运行 `run_eval.py`。
- 若当前本地 API 是按轻量基线方式启动，例如：
```powershell
$env:EMBEDDING_BACKEND="simple"
$env:VECTOR_BACKEND="qdrant"
$env:QDRANT_URL="http://127.0.0.1:6333"
$env:VLLM_ENABLED="false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```
  则建议评测脚本也使用同一套覆盖参数：
```powershell
.\.venv\Scripts\python.exe scripts/run_eval.py --kb-id <kb_id> --eval-file docs/examples/eval_set_academic_affairs_demo_md.json --compare-topk 3,5,8 --compare-threshold none,0.2,0.3 --compare-rerank false,true --embedding-backend simple --vector-backend qdrant --qdrant-url http://127.0.0.1:6333
```

若你希望先从学校官网抓取公开真实语料，再人工筛选入库，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/crawl_suse_public_corpus.py
```
补充说明：
- 当前脚本默认抓取四川轻化工大学主站通知公告、教务处、学生工作部、研究生院、后勤保障部等公开栏目。
- 抓取结果默认写入 `data/crawl/suse_public_<时间戳>/`，页面保存为 Markdown，附件原样下载，并在 `manifest.json` 中记录 `source_uri`。
- 该脚本只抓公开页面与公开附件，不会尝试登录或进入校内权限系统。

若你想减少对主站公告的依赖，优先构建更适合 RAG 的专题语料集，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/crawl_suse_public_corpus.py --profile rag_topics --site-codes jwc,xsc,yjs
```
补充说明：
- `rag_topics` 会提高 `jwc/xsc/yjs` 的抓取配额，并压低主站公告与后勤站点的默认配额。
- `--site-codes jwc,xsc,yjs` 会只抓教务处、学生工作部、研究生院三个专题站点，适合做教务/学工/研究生问答知识库。

若你已经抓到官网公开语料，希望直接做“二次清洗 + 列表页详情补抓 + 自动入库”，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/bootstrap_suse_public_kb.py --crawl-dir data\crawl\suse_public_<时间戳> --kb-name 四川轻化工大学真实官网语料知识库
```
补充说明：
- 该脚本会自动过滤空页、重复页、不可入库格式和超大附件，只保留当前后端支持的 `PDF/DOCX/HTML/Markdown/TXT`。
- 对列表页会再次访问公开详情页，尽量补齐正文级语料；若详情页中引用公开附件，也会一并下载并按可入库规则筛选。
- 清洗结果默认写入 `data/prepared/<crawl_dir_name>_kb_ready/`，并生成 `prepare_report.json` 与 `import_report.json` 便于追踪。
- 若你只想先检查清洗结果、不立即导入，可追加 `--skip-import`。

若你想直接导入 `data/prepared/` 中已经精炼好的真实语料，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/bootstrap_suse_public_kb.py --import-prepared-dir data\prepared\suse_public_20260327_155314_kb_demo_final --kb-name 四川轻化工大学精炼真实语料知识库
```
补充说明：
- 该目录已在仓库内完成二次精炼，保留 381 条较适合答辩演示的真实校园语料。
- 脚本会优先读取 `final_import_summary.json`，直接批量上传到当前 API 对应的 MySQL + Qdrant 环境。


## 9. vLLM 启动说明（可选）
- 本机有 GPU：可本机启动 vLLM
- 没有 GPU：可用远端 vLLM，将 `VLLM_BASE_URL` 指向远端

注意：MVP 阶段可先让 ask 返回固定 mock（仅用于接口联调），正式功能必须接入真实 vLLM。
启用 vLLM 时请设置：
```
VLLM_ENABLED=true
```

若你使用 DeepSeek 作为真实生成模型，可直接按 OpenAI 兼容方式配置：
```
VLLM_ENABLED=true
VLLM_BASE_URL=https://api.deepseek.com/v1
VLLM_MODEL_NAME=deepseek-chat
VLLM_API_KEY=your_deepseek_api_key
```
说明：
- DeepSeek 走 `Authorization: Bearer <API_KEY>` 鉴权。
- 当前后端沿用 OpenAI 兼容的 `POST /chat/completions`，无需额外适配层。

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


## 10. 启用 MySQL 与 Qdrant
1. 安装 MySQL 客户端依赖：
```powershell
.\.venv\Scripts\python.exe -m pip install pymysql qdrant-client
```
2. 设置环境变量：
```
DATABASE_URL=mysql+pymysql://csage:csage123@127.0.0.1:3307/csage?charset=utf8mb4
VECTOR_BACKEND=qdrant
QDRANT_URL=http://127.0.0.1:6333
```
3. 重启服务后即可使用 MySQL 作为关系库、Qdrant 作为向量库。
补充说明：
- 若通过 Docker Compose 启动 `api/worker`，请同时在 `.env` 中配置 `CSAGE_DATABASE_URL_INTERNAL`。
- 若 MySQL 密码包含 `@`、`:`、`/`、`?` 等 URL 保留字符，`CSAGE_DATABASE_URL_INTERNAL` 中必须使用 URL 编码后的密码，避免容器内 `DATABASE_URL` 解析失败。


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
- Compose 中 `api/worker` 默认使用容器内 MySQL 地址：`mysql+pymysql://csage:<password>@mysql:3306/<db>?charset=utf8mb4`。
- 宿主机默认通过 `127.0.0.1:3307` 访问容器内 MySQL，可避免与本机已安装的 MySQL 争抢 3306 端口。
- Compose 读取容器内数据库地址时优先使用 `CSAGE_DATABASE_URL_INTERNAL`；若你自定义了 Compose 的 MySQL 密码，也必须同步更新该值。
- Compose 的 MySQL 初始化变量统一使用 `CSAGE_MYSQL_*` 前缀，避免宿主机上已有的通用 `MYSQL_*` 环境变量污染当前项目。
- Compose 内置了 MySQL 低内存参数（如 `innodb-buffer-pool-size=128M`），用于降低 Docker Desktop 仅分配少量内存时被 `tei/mysql/api/worker` 组合挤爆的概率。
- Compose 中 `api/worker` 已强制使用容器内地址：`QDRANT_URL=http://qdrant:6333`、`REDIS_URL=redis://redis:6379/0`。
- Compose 中 `api/worker` 默认使用容器内 Embedding 地址：`EMBEDDING_BASE_URL=http://tei:80/v1`、`EMBEDDING_API_PATH=/embeddings`，避免容器内误连 `127.0.0.1`。
- 如需自定义容器内 Embedding 地址，可设置 `EMBEDDING_BASE_URL_INTERNAL` 与 `EMBEDDING_API_PATH_INTERNAL`。
- Compose 中 `api/worker` 默认注入 `NO_PROXY=qdrant,tei,redis,localhost,127.0.0.1`，避免本地服务请求被代理劫持。
- Dockerfile 在 `pip install` 构建层会主动清空 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`，避免 Docker Desktop 残留的失效代理导致镜像构建失败。
- 若你必须通过代理访问 PyPI，请先确认 Docker Desktop 的代理地址真实可用；否则应在 Docker Desktop 中关闭全局代理后再执行 `docker compose build`。
- 若未配置 Embedding 服务，Compose 默认回退 `EMBEDDING_BACKEND=simple`，便于本地快速跑通。
- 若你需要 HTTP Embedding，请在 `.env` 中显式设置 `EMBEDDING_BACKEND=http` 与可达的 `EMBEDDING_BASE_URL`。
- 若 `mysql` 或 `tei` 仍频繁出现 `Exited (137)`，优先增加 Docker Desktop 的内存配额；当前仓库默认参数只做“尽量省内存”的保底，不等于无限压缩资源占用。

## 13. 本地演示 SOP（DeepSeek + 本地 TEI）
以下步骤用于演示“真实生成模型 + 本地 Embedding + 引用问答”的完整闭环。

### 13.1 前置配置
1. 复制 `.env.example` 为 `.env`
2. 在 `.env` 中确认以下配置：
```env
VLLM_ENABLED=true
VLLM_BASE_URL=https://api.deepseek.com/v1
VLLM_MODEL_NAME=deepseek-chat
VLLM_API_KEY=your_deepseek_api_key

EMBEDDING_BACKEND=http
EMBEDDING_BASE_URL=http://127.0.0.1:8080/v1
EMBEDDING_API_PATH=/embeddings
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5
VECTOR_DIM=512

DATABASE_URL=mysql+pymysql://csage:csage123@127.0.0.1:3307/csage?charset=utf8mb4
INGEST_QUEUE_ENABLED=true
REDIS_URL=redis://127.0.0.1:6379/0
QDRANT_URL=http://127.0.0.1:6333
```
说明：
- 本机直连 TEI 使用 `http://127.0.0.1:8080/v1`
- 容器内 `api/worker` 会自动改用 `http://tei:80/v1`
- `VLLM_API_KEY` 仅写入本地 `.env`，不得提交

### 13.2 启动服务
1. 启动容器：
```powershell
docker compose up -d mysql qdrant redis tei api worker
```
2. 确认服务状态：
```powershell
docker ps
```
期望看到：
- `campus-sage-mysql-1`
- `campus-sage-api-1`
- `campus-sage-worker-1`
- `campus-sage-tei-1`
- `campus-sage-qdrant-1`
- `campus-sage-redis-1`

3. 启动前端开发服务：
```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 4174
```

### 13.3 打开页面
- 前端：`http://127.0.0.1:4174/login`
- 后端 Swagger：`http://127.0.0.1:8000/docs`
- Qdrant Dashboard：`http://127.0.0.1:6333/dashboard`

### 13.4 登录
默认管理员账号：
```text
邮箱：admin@example.com
密码：Admin1234
```
若本地数据库为空，可执行：
```powershell
.\.venv\Scripts\python.exe scripts/create_admin.py --email admin@example.com --password Admin1234
```

### 13.5 演示流程
1. 登录前端
2. 进入知识库管理页，新建一个知识库
3. 进入文档页，上传真实 PDF 文件
4. 等待入库任务从 `queued` 变为 `succeeded`
5. 进入问答页，选择刚创建的知识库
6. 提交与文档内容一致的问题
7. 检查回答是否满足以下条件：
- 返回 `refusal=false`
- 答案正文包含引用标记，如 `[1]`、`[1][2]`
- 引用区能看到 `doc_name + page/section + snippet`
8. 再提一个知识库中不存在的问题，验证系统拒答：
- 返回 `refusal=true`
- 给出 `refusal_reason`
- 给出下一步建议

### 13.6 常见排查
- 入库任务长期停在 `queued`
- 检查 `worker` 容器是否在运行
- 查看 `docker compose logs -f worker`
- 问答返回 `EMBEDDING_FAILED`
- 检查 `tei` 是否正常启动
- 检查 `.env` 中 `EMBEDDING_BASE_URL` 是否为 `http://127.0.0.1:8080/v1`
- 问答返回 `RAG_MODEL_FAILED`
- 检查 `VLLM_API_KEY` 是否有效
- 检查 `VLLM_BASE_URL` 与 `VLLM_MODEL_NAME` 是否正确
- 前端无法登录
- 检查前端是否从 `http://127.0.0.1:4174` 启动
- 检查 Vite 代理目标是否仍是 `http://127.0.0.1:8000`

## 14. 接口联调脚本（新增）
建议在后端启动后执行以下命令做快速联调：

```powershell
.\.venv\Scripts\python.exe scripts/run_api_smoke.py --base-url http://127.0.0.1:8010 --create-admin-if-missing
```

如需按周产出“smoke + eval”统一报告：

```powershell
.\.venv\Scripts\python.exe scripts/run_weekly_regression.py --base-url http://127.0.0.1:8010 --kb-id <kb_id> --eval-file <eval_json> --topk 5
```

报告默认写入：`data/weekly_regression_<run_id>.json`
