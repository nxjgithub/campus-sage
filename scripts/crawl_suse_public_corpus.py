from __future__ import annotations
# ruff: noqa: E402

import argparse
import hashlib
import json
import mimetypes
import re
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse, urlunparse

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


PAGE_EXTENSIONS = {".htm", ".html", ".jsp", ".psp", ".php", ""}
ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".zip",
    ".rar",
}
BLOCKED_PREFIXES = ("/_css/", "/_js/", "/_upload/tpl/", "/_upload/site/")
BLOCKED_KEYWORDS = ("login", "slogin", "search", "javascript:", "mailto:", "tel:")
DEFAULT_HEADERS = {
    "User-Agent": "CampusSageCrawler/1.0 (+https://www.suse.edu.cn/)",
}


@dataclass(frozen=True, slots=True)
class SeedSite:
    """描述一个公开站点的抓取范围与限制。"""

    name: str
    site_code: str
    allowed_host: str
    seeds: list[str]
    max_pages: int
    max_attachments: int


@dataclass(frozen=True, slots=True)
class CrawlDocument:
    """记录一条已落盘的公开语料。"""

    kind: Literal["page", "attachment"]
    site_code: str
    source_uri: str
    title: str
    local_path: str
    content_type: str | None
    text_length: int | None
    crawled_at: str


class HtmlCorpusParser(HTMLParser):
    """提取 HTML 中的标题、正文文本与链接。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    @property
    def title(self) -> str:
        """返回提取后的页面标题。"""

        return _normalize_whitespace(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        """返回提取后的正文文本。"""

        lines = [
            _normalize_whitespace(item)
            for item in self._text_parts
            if _normalize_whitespace(item)
        ]
        return "\n".join(_dedupe_adjacent(lines))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理标签开始，收集链接并跳过无关区域。"""

        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """处理标签结束。"""

        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        """收集可见文本。"""

        if self._in_title:
            self._title_parts.append(data)
            return
        if self._skip_depth > 0:
            return
        if not data.strip():
            return
        self._text_parts.append(data)


def main() -> None:
    """脚本入口：抓取四川轻化工大学公开语料。"""

    parser = argparse.ArgumentParser(description="抓取四川轻化工大学公开校园语料")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录，默认写入 data/crawl/suse_public_<时间戳>",
    )
    parser.add_argument(
        "--max-pages-per-site",
        type=int,
        default=16,
        help="每个站点最多抓取的 HTML 页面数量",
    )
    parser.add_argument(
        "--max-attachments-per-site",
        type=int,
        default=8,
        help="每个站点最多下载的附件数量",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=250,
        help="相邻请求之间的最小等待毫秒数",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=20.0,
        help="单次请求超时时间",
    )
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT_DIR / "data" / "crawl" / f"suse_public_{_timestamp_slug()}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sites = build_default_sites(
        max_pages=max(1, args.max_pages_per_site),
        max_attachments=max(0, args.max_attachments_per_site),
    )
    all_documents: list[CrawlDocument] = []
    with httpx.Client(
        timeout=max(3.0, args.timeout_s),
        trust_env=False,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        for site in sites:
            all_documents.extend(
                crawl_site(
                    client=client,
                    site=site,
                    output_dir=output_dir,
                    delay_ms=max(0, args.delay_ms),
                )
            )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_count": len(sites),
        "document_count": len(all_documents),
        "documents": [asdict(item) for item in all_documents],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(output_dir), **manifest}, ensure_ascii=False, indent=2))


def build_default_sites(*, max_pages: int, max_attachments: int) -> list[SeedSite]:
    """构建默认抓取站点配置。"""

    return [
        SeedSite(
            name="学校主站通知公告",
            site_code="main_notice",
            allowed_host="www.suse.edu.cn",
            seeds=[
                "https://www.suse.edu.cn/61/list.htm",
            ],
            max_pages=max_pages,
            max_attachments=max_attachments,
        ),
        SeedSite(
            name="教务处",
            site_code="jwc",
            allowed_host="jwc.suse.edu.cn",
            seeds=[
                "http://jwc.suse.edu.cn/3404/list.htm",
                "http://jwc.suse.edu.cn/3408/list.htm",
                "http://jwc.suse.edu.cn/3410/list.htm",
                "http://jwc.suse.edu.cn/tzgg/list.htm",
            ],
            max_pages=max_pages,
            max_attachments=max_attachments,
        ),
        SeedSite(
            name="党委学生工作部",
            site_code="xsc",
            allowed_host="xsc.suse.edu.cn",
            seeds=[
                "http://xsc.suse.edu.cn/tzgg/list.htm",
                "http://xsc.suse.edu.cn/wzgz/list.htm",
                "http://xsc.suse.edu.cn/sxjy/list.htm",
            ],
            max_pages=max_pages,
            max_attachments=max_attachments,
        ),
        SeedSite(
            name="研究生院",
            site_code="yjs",
            allowed_host="yjs.suse.edu.cn",
            seeds=[
                "https://yjs.suse.edu.cn/gsgg/list.htm",
                "https://yjs.suse.edu.cn/bszn/list.htm",
                "https://yjs.suse.edu.cn/gzzd/list.htm",
                "https://yjs.suse.edu.cn/zcfg/list.htm",
            ],
            max_pages=max_pages,
            max_attachments=max_attachments,
        ),
        SeedSite(
            name="后勤保障部",
            site_code="hgc",
            allowed_host="hgc.suse.edu.cn",
            seeds=[
                "http://hgc.suse.edu.cn/1027/list.htm",
                "http://hgc.suse.edu.cn/1033/list.htm",
                "http://hgc.suse.edu.cn/1034/list.htm",
            ],
            max_pages=max_pages,
            max_attachments=max_attachments,
        ),
    ]


def crawl_site(
    *,
    client: httpx.Client,
    site: SeedSite,
    output_dir: Path,
    delay_ms: int,
) -> list[CrawlDocument]:
    """抓取单个站点的公开页面与附件。"""

    site_dir = output_dir / site.site_code
    site_dir.mkdir(parents=True, exist_ok=True)
    queue: deque[str] = deque()
    queued: set[str] = set()
    visited: set[str] = set()
    visited_final: set[str] = set()
    downloaded_attachments: set[str] = set()
    documents: list[CrawlDocument] = []
    last_request_at = 0.0

    for seed in site.seeds:
        normalized = normalize_url(seed, base_url=seed)
        if not normalized:
            continue
        queue.append(normalized)
        queued.add(normalized)

    page_count = 0
    attachment_count = 0
    while queue and page_count < site.max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        _wait_if_needed(delay_ms=delay_ms, last_request_at=last_request_at)
        try:
            response = client.get(url)
        except Exception:
            last_request_at = time.monotonic()
            continue
        last_request_at = time.monotonic()
        if response.status_code != 200:
            continue

        normalized_final_url = normalize_url(str(response.url), base_url=str(response.url))
        if not normalized_final_url or urlparse(normalized_final_url).hostname != site.allowed_host:
            continue
        if normalized_final_url in visited_final:
            continue
        visited_final.add(normalized_final_url)
        if not is_html_response(normalized_final_url, response.headers.get("content-type")):
            if attachment_count >= site.max_attachments:
                continue
            if not is_attachment_url(normalized_final_url):
                continue
            if normalized_final_url in downloaded_attachments:
                continue
            downloaded_attachments.add(normalized_final_url)
            document = save_attachment(
                response=response,
                site=site,
                site_dir=site_dir,
                source_uri=normalized_final_url,
                index=attachment_count + 1,
            )
            if document is not None:
                documents.append(document)
                attachment_count += 1
            continue

        parser = HtmlCorpusParser()
        parser.feed(response.text)
        title = choose_title(parser.title, normalized_final_url)
        primary_fragment = extract_primary_fragment(response.text)
        text = extract_primary_text(response.text, primary_fragment=primary_fragment)
        if should_save_page(text=text, url=normalized_final_url):
            page_count += 1
            document = save_page(
                site=site,
                site_dir=site_dir,
                source_uri=normalized_final_url,
                title=title,
                text=text,
                index=page_count,
                content_type=response.headers.get("content-type"),
            )
            documents.append(document)
        links = extract_content_links(
            html=response.text,
            primary_fragment=primary_fragment,
            base_url=normalized_final_url,
        )
        for link in links:
            if not link:
                continue
            if urlparse(link).hostname != site.allowed_host:
                continue
            if is_attachment_url(link):
                if attachment_count >= site.max_attachments or link in downloaded_attachments:
                    continue
                _wait_if_needed(delay_ms=delay_ms, last_request_at=last_request_at)
                try:
                    file_response = client.get(link)
                except Exception:
                    last_request_at = time.monotonic()
                    continue
                last_request_at = time.monotonic()
                if file_response.status_code != 200:
                    continue
                downloaded_attachments.add(link)
                document = save_attachment(
                    response=file_response,
                    site=site,
                    site_dir=site_dir,
                    source_uri=link,
                    index=attachment_count + 1,
                )
                if document is not None:
                    documents.append(document)
                    attachment_count += 1
                continue
            if not should_visit_page(link, allowed_host=site.allowed_host):
                continue
            if link in queued or link in visited:
                continue
            queue.appendleft(link)
            queued.add(link)
    return documents


def normalize_url(raw_url: str, *, base_url: str) -> str | None:
    """规范化链接，过滤明显无效或非 HTTP 地址。"""

    candidate = (raw_url or "").strip()
    if not candidate:
        return None
    lowered = candidate.lower()
    if any(lowered.startswith(prefix) for prefix in BLOCKED_KEYWORDS):
        return None
    absolute = urljoin(base_url, candidate)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    normalized = parsed._replace(fragment="", params="", query="")
    if normalized.path and any(normalized.path.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return None
    return urlunparse(normalized)


def should_visit_page(url: str, *, allowed_host: str) -> bool:
    """判断链接是否属于可继续抓取的页面。"""

    parsed = urlparse(url)
    if parsed.hostname != allowed_host:
        return False
    if parsed.path and any(part in parsed.path.lower() for part in ("login", "_upload/tpl", "_js/", "_css/")):
        return False
    suffix = Path(parsed.path).suffix.lower()
    return suffix in PAGE_EXTENSIONS


def is_attachment_url(url: str) -> bool:
    """判断链接是否指向可下载附件。"""

    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in ATTACHMENT_EXTENSIONS


def is_html_response(url: str, content_type: str | None) -> bool:
    """根据扩展名和响应头判断是否为 HTML 页面。"""

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in PAGE_EXTENSIONS:
        return True
    if not content_type:
        return False
    lowered = content_type.lower()
    return "text/html" in lowered or "application/xhtml" in lowered


def choose_title(parsed_title: str, source_uri: str) -> str:
    """优先使用页面标题，否则退回 URL 路径生成标题。"""

    if parsed_title:
        return parsed_title
    path = Path(urlparse(source_uri).path)
    candidate = path.stem or path.name or urlparse(source_uri).hostname or "untitled"
    return candidate


def extract_primary_fragment(html: str) -> str | None:
    """优先抽取正文容器或通知列表容器，减少导航噪声。"""

    for marker in ("wp_articlecontent", "paging_content", "news_list"):
        fragment = _extract_balanced_tag(html, marker=marker)
        if fragment:
            return fragment
    return None


def extract_primary_text(html: str, *, primary_fragment: str | None) -> str:
    """从主内容片段中抽取正文或通知列表文本。"""

    if primary_fragment and "news_list" in primary_fragment:
        news_lines = _extract_news_list_lines(primary_fragment)
        if news_lines:
            return "\n".join(news_lines)
    fragment = primary_fragment or html
    parser = HtmlCorpusParser()
    parser.feed(fragment)
    text = parser.text
    return _clean_extracted_text(text)


def extract_content_links(
    *,
    html: str,
    primary_fragment: str | None,
    base_url: str,
) -> list[str]:
    """优先从主内容区提取文章与附件链接。"""

    fragment = primary_fragment or html
    parser = HtmlCorpusParser()
    parser.feed(fragment)
    raw_links = list(parser.links)
    raw_links.extend(re.findall(r"(?:pdfsrc|src|href)=[\"']([^\"']+)[\"']", fragment, re.I))
    links: list[str] = []
    seen: set[str] = set()
    for raw_link in raw_links:
        normalized = normalize_url(raw_link, base_url=base_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        links.append(normalized)
    return links


def should_save_page(*, text: str, url: str) -> bool:
    """过滤过短或明显无效的页面文本。"""

    if len(text) >= 120:
        return True
    return "page.htm" in url or "list.htm" in url


def save_page(
    *,
    site: SeedSite,
    site_dir: Path,
    source_uri: str,
    title: str,
    text: str,
    index: int,
    content_type: str | None,
) -> CrawlDocument:
    """将 HTML 页面保存为 Markdown 文本语料。"""

    page_dir = site_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    filename = f"page_{index:03d}_{short_hash(source_uri)}.md"
    content = "\n".join(
        [
            f"# {title}",
            "",
            f"- 来源：{source_uri}",
            f"- 抓取时间：{datetime.now(timezone.utc).isoformat()}",
            "",
            "## 正文",
            "",
            text,
            "",
        ]
    )
    path = page_dir / filename
    path.write_text(content, encoding="utf-8")
    return CrawlDocument(
        kind="page",
        site_code=site.site_code,
        source_uri=source_uri,
        title=title,
        local_path=str(path.relative_to(ROOT_DIR)),
        content_type=content_type,
        text_length=len(text),
        crawled_at=datetime.now(timezone.utc).isoformat(),
    )


def save_attachment(
    *,
    response: httpx.Response,
    site: SeedSite,
    site_dir: Path,
    source_uri: str,
    index: int,
) -> CrawlDocument | None:
    """将公开附件落盘保存。"""

    attachment_dir = site_dir / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(source_uri)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in ATTACHMENT_EXTENSIONS:
        guessed = mimetypes.guess_extension(response.headers.get("content-type", "").split(";")[0].strip())
        suffix = guessed or ".bin"
    filename = f"attachment_{index:03d}_{short_hash(source_uri)}{suffix}"
    path = attachment_dir / filename
    if not response.content:
        return None
    path.write_bytes(response.content)
    title = Path(parsed.path).name or filename
    return CrawlDocument(
        kind="attachment",
        site_code=site.site_code,
        source_uri=source_uri,
        title=title,
        local_path=str(path.relative_to(ROOT_DIR)),
        content_type=response.headers.get("content-type"),
        text_length=None,
        crawled_at=datetime.now(timezone.utc).isoformat(),
    )


def short_hash(value: str) -> str:
    """为 URL 生成稳定短哈希，避免文件名冲突。"""

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _normalize_whitespace(text: str) -> str:
    """统一压缩空白字符。"""

    return re.sub(r"\s+", " ", text).strip()


def _dedupe_adjacent(items: list[str]) -> list[str]:
    """去掉相邻重复文本，减少导航类噪声。"""

    result: list[str] = []
    for item in items:
        if result and result[-1] == item:
            continue
        result.append(item)
    return result


def _extract_balanced_tag(html: str, *, marker: str) -> str | None:
    """围绕命中的 class 或 id 标记提取平衡的 div/ul 容器。"""

    marker_index = html.find(marker)
    if marker_index == -1:
        return None
    start_div = html.rfind("<div", 0, marker_index)
    start_ul = html.rfind("<ul", 0, marker_index)
    if start_ul > start_div:
        return _extract_balanced_block(html, start=start_ul, open_tag="ul")
    if start_div != -1:
        return _extract_balanced_block(html, start=start_div, open_tag="div")
    return None


def _extract_balanced_block(html: str, *, start: int, open_tag: str) -> str | None:
    """按标签计数提取平衡块。"""

    open_pattern = f"<{open_tag}"
    close_pattern = f"</{open_tag}>"
    depth = 0
    index = start
    while index < len(html):
        next_open = html.find(open_pattern, index)
        next_close = html.find(close_pattern, index)
        if next_close == -1:
            return None
        if next_open != -1 and next_open < next_close:
            depth += 1
            index = next_open + len(open_pattern)
            continue
        depth -= 1
        index = next_close + len(close_pattern)
        if depth <= 0:
            return html[start:index]
    return None


def _extract_news_list_lines(fragment: str) -> list[str]:
    """从通知列表块中抽取“标题 + 日期”摘要。"""

    items = re.findall(r"<li[^>]*class=[\"'][^\"']*news[^\"']*[\"'][^>]*>(.*?)</li>", fragment, re.I | re.S)
    lines: list[str] = []
    for item in items:
        title_match = re.search(r"title=[\"']([^\"']+)[\"']", item, re.I)
        if title_match:
            title = _normalize_whitespace(title_match.group(1))
        else:
            anchor_match = re.search(r"<a[^>]*>(.*?)</a>", item, re.I | re.S)
            title = _normalize_whitespace(re.sub(r"<[^>]+>", "", anchor_match.group(1))) if anchor_match else ""
        date_match = re.search(r"(\d{4}[年.-]\d{1,2}[月.-]\d{1,2}日?)", item)
        if not date_match:
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", item)
        date_text = _normalize_whitespace(date_match.group(1)) if date_match else ""
        if not title:
            continue
        lines.append(f"{title} | {date_text}".strip(" |"))
    return _dedupe_adjacent(lines)


def _clean_extracted_text(text: str) -> str:
    """对抽取文本做轻量清洗，去掉分页与页脚噪声。"""

    blocked_prefixes = (
        "当前位置",
        "每页",
        "记录",
        "第一页",
        "<<上一页",
        "下一页>>",
        "尾页",
        "页码",
        "跳转到",
        "学校地址",
        "Copyright",
    )
    cleaned: list[str] = []
    for line in text.splitlines():
        normalized = _normalize_whitespace(line)
        if not normalized:
            continue
        if normalized in {"首页", "旧版入口"}:
            continue
        if any(normalized.startswith(prefix) for prefix in blocked_prefixes):
            continue
        cleaned.append(normalized)
    return "\n".join(_dedupe_adjacent(cleaned))


def _wait_if_needed(*, delay_ms: int, last_request_at: float) -> None:
    """在相邻请求之间加入轻量等待。"""

    if delay_ms <= 0 or last_request_at <= 0:
        return
    elapsed = (time.monotonic() - last_request_at) * 1000
    if elapsed < delay_ms:
        time.sleep((delay_ms - elapsed) / 1000)


def _timestamp_slug() -> str:
    """生成输出目录使用的时间戳片段。"""

    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    main()
