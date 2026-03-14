from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}


@dataclass(frozen=True, slots=True)
class UploadResult:
    """记录单个示例文档上传后的文档与任务标识。"""

    doc_name: str
    doc_id: str
    job_id: str


def main() -> None:
    """脚本入口：创建示例知识库、上传示例语料并等待入库完成。"""

    parser = argparse.ArgumentParser(description="导入高校教务示例知识库")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="CampusSage API 地址",
    )
    parser.add_argument(
        "--email",
        default="admin@example.com",
        help="管理员邮箱",
    )
    parser.add_argument(
        "--password",
        default="Admin1234",
        help="管理员密码",
    )
    parser.add_argument(
        "--kb-name",
        default="高校教务示例知识库",
        help="新建知识库名称",
    )
    parser.add_argument(
        "--corpus-dir",
        default="docs/examples/academic_demo_corpus",
        help="示例语料目录",
    )
    parser.add_argument(
        "--visibility",
        default="internal",
        choices=["public", "internal", "admin"],
        help="知识库可见性",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="HTTP 请求超时时间",
    )
    parser.add_argument(
        "--poll-interval-s",
        type=float,
        default=1.0,
        help="轮询入库任务状态的间隔秒数",
    )
    parser.add_argument(
        "--wait-timeout-s",
        type=float,
        default=180.0,
        help="等待全部入库完成的最长时间",
    )
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    files = list_corpus_files(corpus_dir)
    if not files:
        raise SystemExit(f"示例语料目录为空：{corpus_dir}")

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout_s,
        trust_env=False,
    ) as client:
        token = login(client, email=args.email, password=args.password)
        client.headers["Authorization"] = f"Bearer {token}"
        kb_id = create_kb(
            client,
            name=args.kb_name,
            description="用于第二阶段检索优化与评测实验的示例知识库",
            visibility=args.visibility,
        )
        uploads = [upload_document(client, kb_id=kb_id, file_path=file_path) for file_path in files]
        jobs = wait_for_jobs(
            client,
            job_ids=[item.job_id for item in uploads],
            poll_interval_s=max(0.2, args.poll_interval_s),
            wait_timeout_s=max(5.0, args.wait_timeout_s),
        )

    output = {
        "kb_id": kb_id,
        "kb_name": args.kb_name,
        "uploaded_count": len(uploads),
        "documents": [
            {
                "doc_name": item.doc_name,
                "doc_id": item.doc_id,
                "job_id": item.job_id,
                "job_status": jobs[item.job_id]["status"],
            }
            for item in uploads
        ],
        "eval_file": "docs/examples/eval_set_academic_affairs_demo_md.json",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def list_corpus_files(corpus_dir: Path) -> list[Path]:
    """收集并排序示例语料文件，过滤非支持格式。"""

    if not corpus_dir.exists():
        return []
    files = [
        path
        for path in corpus_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda item: item.name)


def login(client: httpx.Client, *, email: str, password: str) -> str:
    """登录 API 并返回访问令牌。"""

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    response.raise_for_status()
    data = response.json()
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("登录成功但未返回 access_token")
    return token


def create_kb(
    client: httpx.Client,
    *,
    name: str,
    description: str,
    visibility: str,
) -> str:
    """创建示例知识库并返回 kb_id。"""

    response = client.post(
        "/api/v1/kb",
        json={
            "name": name,
            "description": description,
            "visibility": visibility,
            "config": {
                "topk": 5,
                "threshold": 0.25,
                "rerank_enabled": True,
                "max_context_tokens": 3000,
                "min_evidence_chunks": 1,
                "min_context_chars": 20,
                "min_keyword_coverage": 0.3,
            },
        },
    )
    response.raise_for_status()
    data = response.json()
    kb_id = str(data.get("kb_id") or "").strip()
    if not kb_id:
        raise RuntimeError("创建知识库成功但未返回 kb_id")
    return kb_id


def upload_document(
    client: httpx.Client,
    *,
    kb_id: str,
    file_path: Path,
) -> UploadResult:
    """上传单个示例文档，并返回文档与任务标识。"""

    with file_path.open("rb") as file_obj:
        response = client.post(
            f"/api/v1/kb/{kb_id}/documents",
            data={"doc_name": file_path.name},
            files={"file": (file_path.name, file_obj)},
        )
    response.raise_for_status()
    data = response.json()
    doc = data.get("doc") or {}
    job = data.get("job") or {}
    return UploadResult(
        doc_name=file_path.name,
        doc_id=str(doc.get("doc_id") or ""),
        job_id=str(job.get("job_id") or ""),
    )


def wait_for_jobs(
    client: httpx.Client,
    *,
    job_ids: list[str],
    poll_interval_s: float,
    wait_timeout_s: float,
) -> dict[str, dict]:
    """轮询入库任务，直到全部进入终态或超时。"""

    deadline = time.time() + wait_timeout_s
    results: dict[str, dict] = {}
    pending = set(job_ids)
    while pending:
        if time.time() > deadline:
            raise TimeoutError(f"等待入库任务超时：{sorted(pending)}")
        for job_id in list(pending):
            response = client.get(f"/api/v1/ingest/jobs/{job_id}")
            response.raise_for_status()
            payload = response.json()
            results[job_id] = payload
            if is_terminal_job_status(str(payload.get("status") or "")):
                pending.remove(job_id)
        if pending:
            time.sleep(poll_interval_s)
    return results


def is_terminal_job_status(status: str) -> bool:
    """判断入库任务是否已进入终态。"""

    return status in {"completed", "succeeded", "failed", "canceled"}


if __name__ == "__main__":
    main()
