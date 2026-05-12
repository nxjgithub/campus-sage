from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class UploadResult:
    """记录正式文件上传后的文档与任务标识。"""

    doc_name: str
    doc_id: str
    job_id: str
    source_path: str


def main() -> None:
    """根据 V11 语料清单创建正式文件知识库并上传文档。"""

    parser = argparse.ArgumentParser(description="导入正式文件扩展实验知识库")
    parser.add_argument("--manifest-file", default="docs/examples/official_formal_corpus_v11_manifest.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="CampusSage API 地址")
    parser.add_argument("--email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument("--password", default="Admin1234", help="管理员密码")
    parser.add_argument("--kb-name", default="CampusSage正式文件扩展知识库V11", help="新建知识库名称")
    parser.add_argument("--visibility", default="internal", choices=["public", "internal", "admin"])
    parser.add_argument("--timeout-s", type=float, default=60.0, help="HTTP 请求超时时间")
    parser.add_argument("--poll-interval-s", type=float, default=2.0, help="轮询入库任务间隔")
    parser.add_argument("--wait-timeout-s", type=float, default=1800.0, help="等待入库完成的最长时间")
    args = parser.parse_args()

    manifest_path = ROOT_DIR / args.manifest_file
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents") or []
    if not documents:
        raise SystemExit(f"语料清单没有可导入文档：{manifest_path}")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout_s, trust_env=False) as client:
        token = login(client, email=args.email, password=args.password)
        client.headers["Authorization"] = f"Bearer {token}"
        kb_id = create_kb(client, name=args.kb_name, visibility=args.visibility)
        uploads = [
            upload_document(client, kb_id=kb_id, document=document)
            for document in documents
        ]
        jobs = wait_for_jobs(
            client,
            job_ids=[item.job_id for item in uploads],
            poll_interval_s=max(0.5, args.poll_interval_s),
            wait_timeout_s=max(30.0, args.wait_timeout_s),
        )

    output = {
        "kb_id": kb_id,
        "kb_name": args.kb_name,
        "manifest_file": str(manifest_path.relative_to(ROOT_DIR)),
        "eval_file": "docs/examples/eval_set_official_formal_v11.json",
        "uploaded_count": len(uploads),
        "succeeded_count": sum(1 for item in uploads if jobs[item.job_id]["status"] in {"completed", "succeeded"}),
        "failed_count": sum(1 for item in uploads if jobs[item.job_id]["status"] == "failed"),
        "documents": [
            {
                "doc_name": item.doc_name,
                "source_path": item.source_path,
                "doc_id": item.doc_id,
                "job_id": item.job_id,
                "job_status": jobs[item.job_id]["status"],
            }
            for item in uploads
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def login(client: httpx.Client, *, email: str, password: str) -> str:
    """登录 API 并返回访问令牌。"""

    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    token = str(response.json().get("access_token") or "").strip()
    if not token:
        raise RuntimeError("登录成功但未返回 access_token")
    return token


def create_kb(client: httpx.Client, *, name: str, visibility: str) -> str:
    """创建正式文件实验知识库。"""

    response = client.post(
        "/api/v1/kb",
        json={
            "name": name,
            "description": "基于 data/正式文件 的 V11 扩展实验知识库，用于验证真实校园材料检索与重排效果。",
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
    kb_id = str(response.json().get("kb_id") or "").strip()
    if not kb_id:
        raise RuntimeError("创建知识库成功但未返回 kb_id")
    return kb_id


def upload_document(client: httpx.Client, *, kb_id: str, document: dict[str, Any]) -> UploadResult:
    """上传语料清单中的单个正式文件。"""

    source_path = str(document["source_path"])
    file_path = ROOT_DIR / source_path
    with file_path.open("rb") as file_obj:
        response = client.post(
            f"/api/v1/kb/{kb_id}/documents",
            data={"doc_name": file_path.name},
            files={"file": (file_path.name, file_obj)},
        )
    response.raise_for_status()
    payload = response.json()
    doc = payload.get("doc") or {}
    job = payload.get("job") or {}
    return UploadResult(
        doc_name=file_path.name,
        source_path=source_path,
        doc_id=str(doc.get("doc_id") or ""),
        job_id=str(job.get("job_id") or ""),
    )


def wait_for_jobs(
    client: httpx.Client,
    *,
    job_ids: list[str],
    poll_interval_s: float,
    wait_timeout_s: float,
) -> dict[str, dict[str, Any]]:
    """轮询入库任务，直到全部进入终态或超时。"""

    deadline = time.time() + wait_timeout_s
    results: dict[str, dict[str, Any]] = {}
    pending = set(job_ids)
    while pending:
        if time.time() > deadline:
            raise TimeoutError(f"等待入库任务超时：{sorted(pending)}")
        for job_id in list(pending):
            response = client.get(f"/api/v1/ingest/jobs/{job_id}")
            response.raise_for_status()
            payload = response.json()
            results[job_id] = payload
            if str(payload.get("status") or "") in {"completed", "succeeded", "failed", "canceled"}:
                pending.remove(job_id)
        if pending:
            time.sleep(poll_interval_s)
    return results


if __name__ == "__main__":
    main()
