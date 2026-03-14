from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import mimetypes
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ingest.parser import DocumentParser
from scripts.bootstrap_demo_academic_kb import create_kb, is_terminal_job_status, login
from scripts.crawl_suse_public_corpus import (
    ATTACHMENT_EXTENSIONS,
    DEFAULT_HEADERS,
    HtmlCorpusParser,
    choose_title,
    extract_content_links,
    extract_primary_fragment,
    extract_primary_text,
    is_attachment_url,
    is_html_response,
    normalize_url,
    short_hash,
    should_visit_page,
)


GENERIC_TITLES = {
    "通知公告",
    "公示公告",
    "管理制度",
    "校历作息",
    "规章制度",
}
DATE_PATTERN = re.compile(r"(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?)")
ATTACHMENT_NAME_PATTERN = re.compile(
    r"([^\n|]{4,}?\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt|txt))",
    re.I,
)
OPAQUE_ATTACHMENT_STEM_PATTERN = re.compile(
    r"^[0-9a-f]{8}(?:[-_][0-9a-f]{4}){3}[-_][0-9a-f]{12}$",
    re.I,
)
INGEST_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}
PARSER = DocumentParser()


@dataclass(frozen=True, slots=True)
class CrawledRecord:
    """描述抓取阶段已经落盘的一条语料记录。"""

    kind: str
    site_code: str
    source_uri: str
    title: str
    local_path: str
    content_type: str | None
    text_length: int | None
    crawled_at: str


@dataclass(frozen=True, slots=True)
class SavedPage:
    """描述从抓取 Markdown 中解析出的页面正文。"""

    site_code: str
    title: str
    source_uri: str
    body: str
    local_path: Path


@dataclass(frozen=True, slots=True)
class PreparedCorpusDocument:
    """描述清洗后准备用于入库的一条文档。"""

    kind: str
    site_code: str
    doc_name: str
    source_uri: str
    local_path: str
    origin: str
    published_at: str | None
    text_length: int | None


@dataclass(frozen=True, slots=True)
class SkipRecord:
    """描述被清洗阶段丢弃的记录与原因。"""

    source_uri: str
    reason: str


@dataclass(frozen=True, slots=True)
class UploadResult:
    """记录单个清洗后文档上传后的文档与任务标识。"""

    doc_name: str
    doc_id: str
    job_id: str
    source_uri: str


def main() -> None:
    """脚本入口：清洗已抓取的官网语料、补抓详情页，并自动导入知识库。"""

    configure_stdout()
    parser = argparse.ArgumentParser(description="清洗四川轻化工大学公开语料并自动导入知识库")
    parser.add_argument(
        "--crawl-dir",
        default=None,
        help="已抓取语料目录，默认自动选择 data/crawl 下最新的 suse_public_*",
    )
    parser.add_argument(
        "--prepared-dir",
        default=None,
        help="清洗后的语料输出目录，默认写入 data/prepared/<crawl_dir_name>_kb_ready",
    )
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
        default="四川轻化工大学公开校园语料知识库",
        help="新建知识库名称",
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
        "--delay-ms",
        type=int,
        default=150,
        help="补抓详情页与附件时的最小等待毫秒数",
    )
    parser.add_argument(
        "--max-detail-pages-per-list",
        type=int,
        default=6,
        help="每个列表页最多补抓的详情页数量",
    )
    parser.add_argument(
        "--max-upload-mb",
        type=int,
        default=30,
        help="清洗阶段保留的单文件最大大小（MB），默认与后端上传限制一致",
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
        default=300.0,
        help="等待全部入库完成的最长时间",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="只清洗与补抓，不创建知识库也不上传",
    )
    args = parser.parse_args()

    crawl_dir = resolve_crawl_dir(args.crawl_dir)
    prepared_dir = (
        Path(args.prepared_dir)
        if args.prepared_dir
        else ROOT_DIR / "data" / "prepared" / f"{crawl_dir.name}_kb_ready"
    )
    if not prepared_dir.is_absolute():
        prepared_dir = ROOT_DIR / prepared_dir
    prepared_dir.mkdir(parents=True, exist_ok=True)

    records = load_crawl_manifest(crawl_dir)
    with httpx.Client(
        timeout=max(3.0, args.timeout_s),
        trust_env=False,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        prepared_documents, skipped = prepare_corpus(
            client=client,
            records=records,
            prepared_dir=prepared_dir,
            delay_ms=max(0, args.delay_ms),
            max_detail_pages_per_list=max(1, args.max_detail_pages_per_list),
            max_upload_bytes=max(1, args.max_upload_mb) * 1024 * 1024,
        )

    report = build_prepare_report(
        crawl_dir=crawl_dir,
        prepared_dir=prepared_dir,
        prepared_documents=prepared_documents,
        skipped=skipped,
    )

    if args.skip_import:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=max(3.0, args.timeout_s),
        trust_env=False,
        follow_redirects=True,
    ) as client:
        token = login(client, email=args.email, password=args.password)
        client.headers["Authorization"] = f"Bearer {token}"
        kb_id = create_kb(
            client,
            name=args.kb_name,
            description="基于四川轻化工大学公开官网语料自动清洗与补抓生成",
            visibility=args.visibility,
        )
        uploads = [
            upload_prepared_document(client, kb_id=kb_id, document=item)
            for item in prepared_documents
        ]
        jobs = wait_for_jobs(
            client,
            job_ids=[item.job_id for item in uploads],
            poll_interval_s=max(0.2, args.poll_interval_s),
            wait_timeout_s=max(5.0, args.wait_timeout_s),
        )

    report["kb_id"] = kb_id
    report["kb_name"] = args.kb_name
    report["uploaded_count"] = len(uploads)
    report["uploads"] = [
        {
            "doc_name": item.doc_name,
            "doc_id": item.doc_id,
            "job_id": item.job_id,
            "job_status": jobs[item.job_id]["status"],
            "source_uri": item.source_uri,
        }
        for item in uploads
    ]
    (prepared_dir / "import_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def resolve_crawl_dir(raw_path: str | None) -> Path:
    """解析抓取目录；未显式指定时自动选择最新目录。"""

    if raw_path:
        target = Path(raw_path)
        if not target.is_absolute():
            target = ROOT_DIR / raw_path
        if not target.exists():
            raise SystemExit(f"抓取目录不存在：{target}")
        return target

    candidates = sorted((ROOT_DIR / "data" / "crawl").glob("suse_public_*"))
    if not candidates:
        raise SystemExit("未找到任何 suse_public_* 抓取目录")
    return candidates[-1]


def load_crawl_manifest(crawl_dir: Path) -> list[CrawledRecord]:
    """读取抓取清单并转换为结构化记录。"""

    manifest_path = crawl_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"抓取清单不存在：{manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [CrawledRecord(**item) for item in payload.get("documents", [])]


def prepare_corpus(
    *,
    client: httpx.Client,
    records: list[CrawledRecord],
    prepared_dir: Path,
    delay_ms: int,
    max_detail_pages_per_list: int,
    max_upload_bytes: int,
) -> tuple[list[PreparedCorpusDocument], list[SkipRecord]]:
    """执行语料二次清洗、详情补抓、附件保留与结果落盘。"""

    prepared_documents: list[PreparedCorpusDocument] = []
    skipped: list[SkipRecord] = []
    seen_sources: set[str] = set()
    seen_page_hashes: set[str] = set()
    seen_attachment_hashes: set[str] = set()
    attachment_title_map = build_attachment_title_map(records)

    pages = [parse_saved_page(record) for record in records if record.kind == "page"]
    attachments = [record for record in records if record.kind == "attachment"]

    for page in pages:
        if not page.body.strip():
            skipped.append(SkipRecord(source_uri=page.source_uri, reason="empty_page"))
            continue
        if is_list_page(page):
            enriched_documents, enriched_skipped = enrich_list_page(
                client=client,
                page=page,
                prepared_dir=prepared_dir,
                seen_sources=seen_sources,
                seen_page_hashes=seen_page_hashes,
                seen_attachment_hashes=seen_attachment_hashes,
                delay_ms=delay_ms,
                max_detail_pages=max_detail_pages_per_list,
                max_upload_bytes=max_upload_bytes,
            )
            prepared_documents.extend(enriched_documents)
            skipped.extend(enriched_skipped)
            if not enriched_documents:
                fallback_documents = persist_list_entries(
                    page=page,
                    prepared_dir=prepared_dir,
                    seen_sources=seen_sources,
                    seen_page_hashes=seen_page_hashes,
                )
                if fallback_documents:
                    prepared_documents.extend(fallback_documents)
                else:
                    skipped.append(SkipRecord(source_uri=page.source_uri, reason="list_page_without_detail"))
            continue

        prepared = persist_article_page(
            site_code=page.site_code,
            title=page.title,
            source_uri=page.source_uri,
            body=page.body,
            prepared_dir=prepared_dir,
            origin="crawl_page",
            seen_sources=seen_sources,
            seen_page_hashes=seen_page_hashes,
        )
        if prepared is None:
            skipped.append(SkipRecord(source_uri=page.source_uri, reason="duplicate_or_short_page"))
            continue
        prepared_documents.append(prepared)

    for record in attachments:
        prepared = persist_attachment_from_record(
            record=record,
            prepared_dir=prepared_dir,
            inferred_name=attachment_title_map.get(record.source_uri),
            seen_sources=seen_sources,
            seen_attachment_hashes=seen_attachment_hashes,
            max_upload_bytes=max_upload_bytes,
        )
        if prepared is None:
            skipped.append(SkipRecord(source_uri=record.source_uri, reason="duplicate_or_empty_attachment"))
            continue
        prepared_documents.append(prepared)

    prepared_documents.sort(key=lambda item: (item.site_code, item.doc_name, item.local_path))
    return prepared_documents, skipped


def parse_saved_page(record: CrawledRecord) -> SavedPage:
    """从抓取阶段保存的 Markdown 中解析标题、来源与正文。"""

    file_path = ROOT_DIR / record.local_path
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = record.title
    source_uri = record.source_uri
    body_lines: list[str] = []
    in_body = False
    for raw_line in lines:
        line = raw_line.strip()
        if raw_line.startswith("# "):
            title = raw_line[2:].strip() or title
            continue
        if line.startswith("- 来源"):
            _, _, value = raw_line.partition("：")
            source_uri = value.strip() or source_uri
            continue
        if line == "## 正文":
            in_body = True
            continue
        if in_body:
            body_lines.append(raw_line)
    body = "\n".join(body_lines).strip()
    return SavedPage(
        site_code=record.site_code,
        title=title,
        source_uri=source_uri,
        body=body,
        local_path=file_path,
    )


def is_list_page(page: SavedPage) -> bool:
    """根据正文模式识别公告列表页。"""

    lines = [normalize_text(line) for line in page.body.splitlines() if normalize_text(line)]
    if not lines:
        return False
    dated_lines = [line for line in lines if looks_like_notice_line(line)]
    if dated_lines and len(dated_lines) >= max(4, int(len(lines) * 0.7)):
        return True
    return page.title.strip() in GENERIC_TITLES and len(lines) >= 6 and all(len(line) <= 120 for line in lines)


def looks_like_notice_line(line: str) -> bool:
    """判断一行文本是否近似“标题 | 日期”的公告列表项。"""

    if "|" not in line:
        return False
    return DATE_PATTERN.search(line) is not None


def build_attachment_title_map(records: list[CrawledRecord]) -> dict[str, str]:
    """从已抓取页面中推断附件的人类可读名称。"""

    site_candidates: dict[str, set[str]] = {}
    for record in records:
        if record.kind != "page":
            continue
        page = parse_saved_page(record)
        for match in ATTACHMENT_NAME_PATTERN.findall(page.body):
            candidate = normalize_text(match)
            if not candidate:
                continue
            site_candidates.setdefault(record.site_code, set()).add(candidate)

    result: dict[str, str] = {}
    for record in records:
        if record.kind != "attachment":
            continue
        suffix = Path(urlparse(record.source_uri).path).suffix.lower()
        candidates = [
            item
            for item in sorted(site_candidates.get(record.site_code, set()))
            if item.lower().endswith(suffix)
        ]
        if len(candidates) == 1:
            result[record.source_uri] = candidates[0]
    return result


def enrich_list_page(
    *,
    client: httpx.Client,
    page: SavedPage,
    prepared_dir: Path,
    seen_sources: set[str],
    seen_page_hashes: set[str],
    seen_attachment_hashes: set[str],
    delay_ms: int,
    max_detail_pages: int,
    max_upload_bytes: int,
) -> tuple[list[PreparedCorpusDocument], list[SkipRecord]]:
    """针对列表页补抓详情页与附件，优先生成正文级语料。"""

    documents: list[PreparedCorpusDocument] = []
    skipped: list[SkipRecord] = []
    response = safe_get(client, page.source_uri, delay_ms=delay_ms)
    if response is None or response.status_code != 200:
        skipped.append(SkipRecord(source_uri=page.source_uri, reason="list_fetch_failed"))
        return documents, skipped

    normalized_page_url = normalize_url(str(response.url), base_url=str(response.url))
    if not normalized_page_url:
        skipped.append(SkipRecord(source_uri=page.source_uri, reason="invalid_list_url"))
        return documents, skipped

    primary_fragment = extract_primary_fragment(response.text)
    links = extract_content_links(
        html=response.text,
        primary_fragment=primary_fragment,
        base_url=normalized_page_url,
    )

    detail_count = 0
    for link in links:
        normalized_link = normalize_url(link, base_url=normalized_page_url)
        if not normalized_link:
            continue
        if is_attachment_url(normalized_link):
            attachment = download_attachment(
                client=client,
                source_uri=normalized_link,
                site_code=page.site_code,
                prepared_dir=prepared_dir,
                origin="enriched_attachment",
                preferred_name=None,
                delay_ms=delay_ms,
                seen_sources=seen_sources,
                seen_attachment_hashes=seen_attachment_hashes,
                max_upload_bytes=max_upload_bytes,
            )
            if attachment is not None:
                documents.append(attachment)
            continue
        if detail_count >= max_detail_pages:
            continue
        if urlparse(normalized_link).hostname != urlparse(normalized_page_url).hostname:
            continue
        if not should_visit_page(normalized_link, allowed_host=urlparse(normalized_page_url).hostname or ""):
            continue
        detail = fetch_detail_page(
            client=client,
            source_uri=normalized_link,
            site_code=page.site_code,
            prepared_dir=prepared_dir,
            delay_ms=delay_ms,
            seen_sources=seen_sources,
            seen_page_hashes=seen_page_hashes,
            seen_attachment_hashes=seen_attachment_hashes,
            max_upload_bytes=max_upload_bytes,
        )
        if detail is None:
            continue
        documents.extend(detail)
        detail_count += 1

    return documents, skipped


def fetch_detail_page(
    *,
    client: httpx.Client,
    source_uri: str,
    site_code: str,
    prepared_dir: Path,
    delay_ms: int,
    seen_sources: set[str],
    seen_page_hashes: set[str],
    seen_attachment_hashes: set[str],
    max_upload_bytes: int,
) -> list[PreparedCorpusDocument] | None:
    """抓取详情页正文，并顺带补抓其附件。"""

    response = safe_get(client, source_uri, delay_ms=delay_ms)
    if response is None or response.status_code != 200:
        return None
    normalized_final_url = normalize_url(str(response.url), base_url=str(response.url))
    if not normalized_final_url:
        return None
    if not is_html_response(normalized_final_url, response.headers.get("content-type")):
        attachment = download_attachment(
            client=client,
            source_uri=normalized_final_url,
            site_code=site_code,
            prepared_dir=prepared_dir,
            origin="enriched_attachment",
            preferred_name=None,
            delay_ms=0,
            seen_sources=seen_sources,
            seen_attachment_hashes=seen_attachment_hashes,
            initial_response=response,
            max_upload_bytes=max_upload_bytes,
        )
        return [attachment] if attachment is not None else None

    parser = HtmlCorpusParser()
    parser.feed(response.text)
    primary_fragment = extract_primary_fragment(response.text)
    text = extract_primary_text(response.text, primary_fragment=primary_fragment)
    title = choose_title(parser.title, normalized_final_url)
    page_document = persist_article_page(
        site_code=site_code,
        title=title,
        source_uri=normalized_final_url,
        body=text,
        prepared_dir=prepared_dir,
        origin="enriched_detail_page",
        seen_sources=seen_sources,
        seen_page_hashes=seen_page_hashes,
    )
    if page_document is None:
        return None

    documents = [page_document]
    links = extract_content_links(
        html=response.text,
        primary_fragment=primary_fragment,
        base_url=normalized_final_url,
    )
    for link in links:
        normalized_link = normalize_url(link, base_url=normalized_final_url)
        if not normalized_link or not is_attachment_url(normalized_link):
            continue
        preferred_name = infer_attachment_name_from_body(text, normalized_link)
        attachment = download_attachment(
            client=client,
            source_uri=normalized_link,
            site_code=site_code,
            prepared_dir=prepared_dir,
            origin="detail_page_attachment",
            preferred_name=preferred_name,
            delay_ms=delay_ms,
            seen_sources=seen_sources,
            seen_attachment_hashes=seen_attachment_hashes,
            max_upload_bytes=max_upload_bytes,
        )
        if attachment is not None:
            documents.append(attachment)
    return documents


def persist_article_page(
    *,
    site_code: str,
    title: str,
    source_uri: str,
    body: str,
    prepared_dir: Path,
    origin: str,
    seen_sources: set[str],
    seen_page_hashes: set[str],
) -> PreparedCorpusDocument | None:
    """将正文级页面落盘为适合入库的 Markdown 文档。"""

    normalized_body = normalize_text_block(body)
    normalized_title = normalize_text(title) or build_title_from_url(source_uri)
    if len(normalized_body) < 120:
        return None
    if source_uri in seen_sources:
        return None
    body_hash = short_hash(normalized_body)
    if body_hash in seen_page_hashes:
        return None

    seen_sources.add(source_uri)
    seen_page_hashes.add(body_hash)
    page_dir = prepared_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(normalized_title)}_{short_hash(source_uri)}.md"
    path = page_dir / filename
    content = "\n".join(
        [
            f"# {normalized_title}",
            "",
            f"- 来源：{source_uri}",
            f"- 站点：{site_code}",
            "- 语料类型：正文页",
            f"- 清洗时间：{datetime.now(timezone.utc).isoformat()}",
            "",
            "## 正文",
            "",
            normalized_body,
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    return PreparedCorpusDocument(
        kind="page",
        site_code=site_code,
        doc_name=normalized_title,
        source_uri=source_uri,
        local_path=str(path.relative_to(ROOT_DIR)),
        origin=origin,
        published_at=extract_first_date(normalized_body),
        text_length=len(normalized_body),
    )


def persist_list_entries(
    *,
    page: SavedPage,
    prepared_dir: Path,
    seen_sources: set[str],
    seen_page_hashes: set[str],
) -> list[PreparedCorpusDocument]:
    """当列表页无法补抓详情时，将列表项拆成独立短文档保底。"""

    documents: list[PreparedCorpusDocument] = []
    for index, line in enumerate([normalize_text(item) for item in page.body.splitlines() if normalize_text(item)], start=1):
        if not looks_like_notice_line(line):
            continue
        title_part, _, date_part = line.partition("|")
        title = normalize_text(title_part)
        published_at = extract_first_date(date_part)
        body = "\n".join(
            [
                "该条语料来自学校公开公告列表页，当前保留的是标题级摘要。",
                f"原始标题：{title}",
                f"发布日期：{published_at or normalize_text(date_part) or '未知'}",
                "如需完整细节，请继续打开原始来源核对正文。",
            ]
        )
        doc = persist_article_page(
            site_code=page.site_code,
            title=title,
            source_uri=f"{page.source_uri}#item-{index}",
            body=body,
            prepared_dir=prepared_dir,
            origin="list_fallback_entry",
            seen_sources=seen_sources,
            seen_page_hashes=seen_page_hashes,
        )
        if doc is None:
            continue
        documents.append(
            PreparedCorpusDocument(
                kind=doc.kind,
                site_code=doc.site_code,
                doc_name=doc.doc_name,
                source_uri=page.source_uri,
                local_path=doc.local_path,
                origin=doc.origin,
                published_at=published_at,
                text_length=doc.text_length,
            )
        )
    return documents


def persist_attachment_from_record(
    *,
    record: CrawledRecord,
    prepared_dir: Path,
    inferred_name: str | None,
    seen_sources: set[str],
    seen_attachment_hashes: set[str],
    max_upload_bytes: int,
) -> PreparedCorpusDocument | None:
    """把抓取阶段已有附件复制到清洗目录。"""

    source_path = ROOT_DIR / record.local_path
    if not source_path.exists() or source_path.stat().st_size == 0:
        return None
    if source_path.suffix.lower() not in INGEST_ALLOWED_EXTENSIONS:
        return None
    if source_path.stat().st_size > max_upload_bytes:
        return None
    content_hash = short_hash(source_path.read_bytes().hex())
    if record.source_uri in seen_sources or content_hash in seen_attachment_hashes:
        return None

    seen_sources.add(record.source_uri)
    seen_attachment_hashes.add(content_hash)
    attachment_dir = prepared_dir / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower()
    display_name = normalize_text(inferred_name or record.title or source_path.name)
    if not display_name.lower().endswith(suffix):
        display_name = f"{display_name}{suffix}"
    if is_opaque_attachment_name(display_name):
        return None
    target_name = f"{slugify(Path(display_name).stem)}_{short_hash(record.source_uri)}{suffix}"
    target_path = attachment_dir / target_name
    target_path.write_bytes(source_path.read_bytes())
    if not is_ingestable_file(target_path):
        target_path.unlink(missing_ok=True)
        return None
    return PreparedCorpusDocument(
        kind="attachment",
        site_code=record.site_code,
        doc_name=display_name,
        source_uri=record.source_uri,
        local_path=str(target_path.relative_to(ROOT_DIR)),
        origin="crawl_attachment",
        published_at=None,
        text_length=None,
    )


def download_attachment(
    *,
    client: httpx.Client,
    source_uri: str,
    site_code: str,
    prepared_dir: Path,
    origin: str,
    preferred_name: str | None,
    delay_ms: int,
    seen_sources: set[str],
    seen_attachment_hashes: set[str],
    max_upload_bytes: int,
    initial_response: httpx.Response | None = None,
) -> PreparedCorpusDocument | None:
    """下载详情页引用的附件并复制到清洗目录。"""

    if source_uri in seen_sources:
        return None
    response = initial_response or safe_get(client, source_uri, delay_ms=delay_ms)
    if response is None or response.status_code != 200 or not response.content:
        return None
    suffix = Path(urlparse(source_uri).path).suffix.lower()
    if suffix not in ATTACHMENT_EXTENSIONS:
        guessed = mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0].strip())
        suffix = guessed or ".bin"
    if suffix not in INGEST_ALLOWED_EXTENSIONS:
        return None
    if len(response.content) > max_upload_bytes:
        return None
    content_hash = short_hash(response.content.hex())
    if content_hash in seen_attachment_hashes:
        return None

    seen_sources.add(source_uri)
    seen_attachment_hashes.add(content_hash)
    attachment_dir = prepared_dir / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    raw_name = preferred_name or Path(urlparse(source_uri).path).name or f"attachment{suffix}"
    display_name = normalize_text(raw_name)
    if not display_name.lower().endswith(suffix):
        display_name = f"{display_name}{suffix}"
    if is_opaque_attachment_name(display_name):
        return None
    file_name = f"{slugify(Path(display_name).stem)}_{short_hash(source_uri)}{suffix}"
    target_path = attachment_dir / file_name
    target_path.write_bytes(response.content)
    if not is_ingestable_file(target_path):
        target_path.unlink(missing_ok=True)
        return None
    return PreparedCorpusDocument(
        kind="attachment",
        site_code=site_code,
        doc_name=display_name,
        source_uri=source_uri,
        local_path=str(target_path.relative_to(ROOT_DIR)),
        origin=origin,
        published_at=None,
        text_length=None,
    )


def infer_attachment_name_from_body(body: str, source_uri: str) -> str | None:
    """尝试从正文里提取人类可读的附件名。"""

    suffix = Path(urlparse(source_uri).path).suffix.lower()
    candidates = [
        normalize_text(match)
        for match in ATTACHMENT_NAME_PATTERN.findall(body)
        if match.lower().endswith(suffix)
    ]
    unique_candidates = sorted(set(candidate for candidate in candidates if candidate))
    if len(unique_candidates) == 1:
        return unique_candidates[0]
    return None


def upload_prepared_document(
    client: httpx.Client,
    *,
    kb_id: str,
    document: PreparedCorpusDocument,
) -> UploadResult:
    """上传清洗后的单个文档并返回文档与任务标识。"""

    file_path = ROOT_DIR / document.local_path
    with file_path.open("rb") as file_obj:
        response = client.post(
            f"/api/v1/kb/{kb_id}/documents",
            data={
                "doc_name": document.doc_name,
                "published_at": document.published_at,
                "source_uri": document.source_uri,
            },
            files={"file": (file_path.name, file_obj)},
        )
    response.raise_for_status()
    data = response.json()
    doc = data.get("doc") or {}
    job = data.get("job") or {}
    return UploadResult(
        doc_name=document.doc_name,
        doc_id=str(doc.get("doc_id") or ""),
        job_id=str(job.get("job_id") or ""),
        source_uri=document.source_uri,
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
            if is_terminal_job_status(str(payload.get("status") or "")):
                pending.remove(job_id)
        if pending:
            time.sleep(poll_interval_s)
    return results


def build_prepare_report(
    *,
    crawl_dir: Path,
    prepared_dir: Path,
    prepared_documents: list[PreparedCorpusDocument],
    skipped: list[SkipRecord],
) -> dict[str, Any]:
    """构建清洗阶段报告并写入磁盘。"""

    report = {
        "crawl_dir": str(crawl_dir),
        "prepared_dir": str(prepared_dir),
        "prepared_count": len(prepared_documents),
        "page_count": sum(1 for item in prepared_documents if item.kind == "page"),
        "attachment_count": sum(1 for item in prepared_documents if item.kind == "attachment"),
        "prepared_documents": [asdict(item) for item in prepared_documents],
        "skipped": [asdict(item) for item in skipped],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (prepared_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def safe_get(client: httpx.Client, source_uri: str, *, delay_ms: int) -> httpx.Response | None:
    """带基础等待与异常兜底的 GET 请求。"""

    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
    try:
        return client.get(source_uri)
    except Exception:
        return None


def configure_stdout() -> None:
    """尽量把标准输出切到 UTF-8，避免 Windows 终端编码阻塞结果输出。"""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def is_ingestable_file(path: Path) -> bool:
    """用后端同一套解析器做预检，提前剔除会在入库阶段失败的文件。"""

    try:
        PARSER.parse(path)
    except Exception:
        return False
    return True


def normalize_text(value: str) -> str:
    """统一压缩空白字符并裁剪首尾空白。"""

    cleaned = (value or "").replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_text_block(value: str) -> str:
    """标准化多行文本，移除过多空行与噪声分隔。"""

    lines = [normalize_text(line) for line in value.splitlines()]
    cleaned_lines: list[str] = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
            continue
        cleaned_lines.append(line)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def extract_first_date(value: str) -> str | None:
    """从文本中提取首个日期字符串。"""

    match = DATE_PATTERN.search(value or "")
    if not match:
        return None
    return match.group(1).replace("年", "-").replace("月", "-").replace("日", "")


def build_title_from_url(source_uri: str) -> str:
    """当页面标题不可用时，根据 URL 退化生成文档名。"""

    path = Path(urlparse(source_uri).path)
    return path.stem or path.name or urlparse(source_uri).hostname or "untitled"


def slugify(value: str) -> str:
    """为清洗后文件生成稳定文件名。"""

    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value).strip("_")
    return slug[:80] or "document"


def is_opaque_attachment_name(value: str) -> bool:
    """识别仅由 UUID/随机串组成的附件名，避免把低价值模板直接入库。"""

    stem = Path(value).stem.strip()
    return OPAQUE_ATTACHMENT_STEM_PATTERN.fullmatch(stem.replace(" ", "")) is not None


if __name__ == "__main__":
    main()
