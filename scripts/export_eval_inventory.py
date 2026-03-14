from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class DocumentInventory:
    """描述单个文档在向量库中的可评测元数据概览。"""

    doc_id: str
    doc_name: str
    source_type: str | None
    chunk_count: int
    page_start_min: int | None
    page_end_max: int | None
    section_path_examples: list[str]


def main() -> None:
    """脚本入口：导出知识库文档清单，辅助对齐离线评测集。"""

    parser = argparse.ArgumentParser(description="导出知识库评测清单")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument(
        "--output",
        default=None,
        help="输出 JSON 文件路径；不传则直接打印到标准输出",
    )
    parser.add_argument(
        "--section-sample-limit",
        type=int,
        default=5,
        help="每个文档保留的章节路径样本数量",
    )
    parser.add_argument(
        "--scroll-limit",
        type=int,
        default=256,
        help="每次向 Qdrant 拉取的滚动批量大小",
    )
    args = parser.parse_args()

    settings = get_settings()
    points = load_qdrant_points(
        kb_id=args.kb_id,
        settings=settings,
        scroll_limit=args.scroll_limit,
    )
    documents = summarize_documents(
        points,
        section_sample_limit=max(1, args.section_sample_limit),
    )
    payload = build_inventory_payload(
        kb_id=args.kb_id,
        collection_name=build_collection_name(
            kb_id=args.kb_id,
            collection_prefix=settings.qdrant_collection_prefix,
        ),
        documents=documents,
    )
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"已写入 {args.output}")
        return
    print(content)


def build_collection_name(kb_id: str, collection_prefix: str) -> str:
    """拼接 Qdrant 集合名，保持与应用运行时一致。"""

    return f"{collection_prefix}{kb_id}"


def load_qdrant_points(
    *,
    kb_id: str,
    settings: Settings,
    scroll_limit: int,
) -> list[dict[str, Any]]:
    """滚动拉取知识库下全部 point payload。"""

    if settings.vector_backend != "qdrant":
        raise ValueError("当前脚本仅支持 qdrant 向量后端")
    if scroll_limit <= 0:
        raise ValueError("scroll_limit 必须大于 0")

    collection_name = build_collection_name(kb_id, settings.qdrant_collection_prefix)
    endpoint = (
        f"{settings.qdrant_url.rstrip('/')}/collections/{collection_name}/points/scroll"
    )
    offset: str | int | None = None
    points: list[dict[str, Any]] = []

    while True:
        batch, offset = _scroll_once(
            endpoint=endpoint,
            offset=offset,
            limit=scroll_limit,
            api_key=settings.qdrant_api_key,
            timeout_s=settings.qdrant_timeout_s,
        )
        points.extend(batch)
        if offset is None:
            break
    return points


def _scroll_once(
    *,
    endpoint: str,
    offset: str | int | None,
    limit: int,
    api_key: str | None,
    timeout_s: int,
) -> tuple[list[dict[str, Any]], str | int | None]:
    """执行单次 scroll 请求并返回 points 与下一页偏移量。"""

    payload: dict[str, Any] = {
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }
    if offset is not None:
        payload["offset"] = offset

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=max(1, timeout_s)) as response:
        data = json.loads(response.read().decode("utf-8"))

    result = data.get("result") or {}
    raw_points = result.get("points") or []
    points = [
        point.get("payload") or {}
        for point in raw_points
        if isinstance(point, dict)
    ]
    return points, result.get("next_page_offset")


def summarize_documents(
    points: list[dict[str, Any]],
    *,
    section_sample_limit: int,
) -> list[DocumentInventory]:
    """按文档聚合 point payload，生成评测清单摘要。"""

    docs: dict[str, dict[str, Any]] = {}
    for payload in points:
        doc_id = str(payload.get("doc_id") or "").strip()
        doc_name = str(payload.get("doc_name") or "").strip()
        if not doc_id or not doc_name:
            continue

        item = docs.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "source_type": _normalize_optional_str(payload.get("source_type")),
                "chunk_count": 0,
                "page_start_min": None,
                "page_end_max": None,
                "section_path_examples": [],
                "_section_seen": set(),
            },
        )
        item["chunk_count"] += 1
        page_start = _coerce_optional_int(payload.get("page_start"))
        page_end = _coerce_optional_int(payload.get("page_end")) or page_start
        if page_start is not None:
            current_min = item["page_start_min"]
            item["page_start_min"] = (
                page_start if current_min is None else min(current_min, page_start)
            )
        if page_end is not None:
            current_max = item["page_end_max"]
            item["page_end_max"] = (
                page_end if current_max is None else max(current_max, page_end)
            )
        section_path = _normalize_optional_str(payload.get("section_path"))
        if (
            section_path
            and section_path not in item["_section_seen"]
            and len(item["section_path_examples"]) < section_sample_limit
        ):
            item["_section_seen"].add(section_path)
            item["section_path_examples"].append(section_path)

    documents = [
        DocumentInventory(
            doc_id=item["doc_id"],
            doc_name=item["doc_name"],
            source_type=item["source_type"],
            chunk_count=item["chunk_count"],
            page_start_min=item["page_start_min"],
            page_end_max=item["page_end_max"],
            section_path_examples=item["section_path_examples"],
        )
        for item in docs.values()
    ]
    documents.sort(key=lambda item: (item.doc_name, item.doc_id))
    return documents


def build_inventory_payload(
    *,
    kb_id: str,
    collection_name: str,
    documents: list[DocumentInventory],
) -> dict[str, Any]:
    """构建导出 JSON，供人工编写评测集时直接参考。"""

    return {
        "kb_id": kb_id,
        "collection_name": collection_name,
        "document_count": len(documents),
        "documents": [asdict(item) for item in documents],
    }


def _normalize_optional_str(value: object) -> str | None:
    """统一清洗可选字符串字段。"""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_optional_int(value: object) -> int | None:
    """尽力将页码字段转换为整数。"""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
