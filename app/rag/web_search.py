from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from app.core.settings import Settings
from app.rag.vector_store import VectorHit


@dataclass(slots=True)
class WebSearchConfig:
    """知识库联网检索配置。"""

    enabled: bool
    allowed_prefixes: list[str]
    seed_urls: list[str]
    topk: int
    search_provider: str
    search_base_url: str | None
    search_api_key: str | None
    search_result_limit: int
    max_pages: int
    timeout_s: int


@dataclass(slots=True)
class SearchResult:
    """联网搜索候选结果。"""

    title: str
    url: str
    snippet: str | None = None


@dataclass(slots=True)
class _WebPage:
    """已抽取的网页内容。"""

    url: str
    title: str
    text: str
    links: list[str]


class WebSearchProvider(Protocol):
    """联网搜索提供方协议。"""

    def search(
        self,
        query: str,
        allowed_prefixes: list[str],
        limit: int,
        timeout_s: int,
    ) -> list[SearchResult]:
        """搜索候选网页 URL。"""


class SeedOnlySearchProvider:
    """不调用外部搜索服务的空提供方。"""

    def search(
        self,
        query: str,
        allowed_prefixes: list[str],
        limit: int,
        timeout_s: int,
    ) -> list[SearchResult]:
        """返回空结果，由 seed URL 抓取兜底。"""

        del query, allowed_prefixes, limit, timeout_s
        return []


class SearxngSearchProvider:
    """SearxNG JSON 搜索提供方。"""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._retry_count = 2  # 最多重试 2 次
        self._retry_delay = 2  # 重试间隔（秒）

    def search(
        self,
        query: str,
        allowed_prefixes: list[str],
        limit: int,
        timeout_s: int,
    ) -> list[SearchResult]:
        """按授权站点执行搜索，并过滤越界 URL。"""

        if not query.strip() or not allowed_prefixes:
            return []
        results: list[SearchResult] = []
        seen: set[str] = set()
        for host in _allowed_hosts(allowed_prefixes):
            if len(results) >= limit:
                break
            # 使用带重试机制的搜索方法
            items = self._search_with_retry(query, host, limit, timeout_s)
            for item in items:
                normalized = _normalize_url(item.url)
                if (
                    normalized is None
                    or normalized in seen
                    or not _is_url_allowed(normalized, allowed_prefixes)
                ):
                    continue
                seen.add(normalized)
                results.append(
                    SearchResult(title=item.title, url=normalized, snippet=item.snippet)
                )
                if len(results) >= limit:
                    break
        return results

    def _search_with_retry(
        self,
        query: str,
        host: str,
        limit: int,
        timeout_s: int,
    ) -> list[SearchResult]:
        """带重试机制的搜索调用，处理限流等临时错误。"""

        import time
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        last_exception = None

        for attempt in range(1, self._retry_count + 1):
            try:
                return self._search_host(query, host, limit, timeout_s)
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()

                # 检测是否为限流错误
                if "429" in error_msg or "too many" in error_msg or "suspended" in error_msg:
                    wait_time = self._retry_delay * attempt
                    logger.warning(
                        f"SearxNG 搜索引擎被限流，{wait_time}秒后重试 "
                        f"(尝试 {attempt}/{self._retry_count}): {query[:50]}..."
                    )
                    time.sleep(wait_time)
                else:
                    # 非限流错误，直接返回空结果
                    logger.error(f"SearxNG 搜索失败: {e}")
                    break

        # 所有重试都失败
        logger.error(
            f"SearxNG 搜索在 {self._retry_count} 次尝试后仍然失败: {last_exception}"
        )
        return []

    def _search_host(
        self,
        query: str,
        host: str,
        limit: int,
        timeout_s: int,
    ) -> list[SearchResult]:
        """调用单个站点限定搜索。"""

        from app.core.logging import get_logger

        logger = get_logger(__name__)
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = httpx.get(
                f"{self._base_url}/search",
                params={
                    "q": f"site:{host} {query}",
                    "format": "json",
                    "language": "zh-CN",
                    "safesearch": 1,
                },
                headers=headers,
                timeout=timeout_s,
                trust_env=False,
            )
        except Exception as e:
            logger.warning(f"SearxNG HTTP 请求失败: {e}")
            return []
        if response.status_code >= 400:
            logger.warning(
                f"SearxNG 返回错误状态码 {response.status_code}: "
                f"{response.text[:200]}"
            )
            return []
        try:
            payload = response.json()
        except Exception as e:
            logger.warning(f"SearxNG 响应解析失败: {e}")
            return []
        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            logger.warning("SearxNG 响应格式异常，未找到 results 字段")
            return []
        results: list[SearchResult] = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(raw.get("title") or "").strip(),
                    url=url,
                    snippet=str(raw.get("content") or "").strip() or None,
                )
            )
            if len(results) >= limit:
                break
        return results


class WebEvidenceRetriever:
    """受控联网证据检索器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._search_provider = _build_search_provider(settings)
        # 新增：简单的内存缓存，避免短时间内重复搜索
        self._cache: dict[str, tuple[list[SearchResult], float]] = {}
        self._cache_ttl = 300  # 缓存有效期 5 分钟

    def retrieve(
        self,
        kb_id: str,
        kb_name: str,
        question: str,
        query: str,
        config: WebSearchConfig,
    ) -> list[VectorHit]:
        """在知识库授权 URL 范围内抓取并构造临时证据。"""

        import time
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        del kb_name
        if not config.enabled or not config.allowed_prefixes:
            return []

        # 检查缓存：相同查询和授权前缀在 5 分钟内直接复用
        cache_key = f"{query}:{'|'.join(sorted(config.allowed_prefixes))}"
        now = time.time()
        search_results: list[SearchResult] = []

        if cache_key in self._cache:
            cached_results, cached_time = self._cache[cache_key]
            if now - cached_time < self._cache_ttl:
                logger.info(f"使用缓存的搜索结果: {query[:50]}...")
                search_results = cached_results
            else:
                # 缓存过期，删除
                del self._cache[cache_key]

        # 如果缓存未命中或已过期，执行搜索
        if not search_results:
            search_results = self._search_provider.search(
                query=query,
                allowed_prefixes=config.allowed_prefixes,
                limit=config.search_result_limit,
                timeout_s=config.timeout_s,
            )
            # 存入缓存
            if search_results:
                self._cache[cache_key] = (search_results, now)
                logger.info(f"搜索结果已缓存: {len(search_results)} 条结果")

        candidates: list[_WebPage] = []
        visited: set[str] = set()
        for result in search_results:
            if len(visited) >= config.max_pages:
                break
            page = self._fetch_page(result.url, config, visited)
            if page is not None:
                candidates.append(page)
        seeds = _dedupe_urls(config.seed_urls or config.allowed_prefixes)
        for seed in seeds:
            if len(visited) >= config.max_pages:
                break
            page = self._fetch_page(seed, config, visited)
            if page is None:
                continue
            candidates.append(page)
            ranked_links = sorted(
                page.links,
                key=lambda item: _score_text(query, item),
                reverse=True,
            )
            for link in ranked_links[: max(0, config.max_pages - len(visited))]:
                if len(visited) >= config.max_pages:
                    break
                linked_page = self._fetch_page(link, config, visited)
                if linked_page is not None:
                    candidates.append(linked_page)
        ranked_pages = sorted(
            candidates,
            key=lambda item: _score_text(query or question, f"{item.title}\n{item.text}"),
            reverse=True,
        )
        hits: list[VectorHit] = []
        for page in ranked_pages:
            score = _score_text(query or question, f"{page.title}\n{page.text}")
            if score <= 0:
                continue
            text = _trim_text(page.text, max_chars=max(800, self._settings.chunk_size * 2))
            if len(text) < 20:
                continue
            payload = _build_web_payload(kb_id=kb_id, page=page, text=text)
            hits.append(VectorHit(score=min(1.0, score), payload=payload))
            if len(hits) >= config.topk:
                break
        return hits

    def _fetch_page(
        self,
        url: str,
        config: WebSearchConfig,
        visited: set[str],
    ) -> _WebPage | None:
        """抓取单个网页，并强制校验授权范围和重定向结果。"""

        normalized = _normalize_url(url)
        if normalized is None or normalized in visited:
            return None
        if not _is_url_allowed(normalized, config.allowed_prefixes):
            return None
        visited.add(normalized)
        try:
            response = httpx.get(
                normalized,
                follow_redirects=True,
                timeout=config.timeout_s,
                headers={"User-Agent": "CampusSage-WebEvidence/0.1"},
                trust_env=False,
            )
        except Exception:
            return None
        final_url = str(response.url)
        if not _is_url_allowed(final_url, config.allowed_prefixes):
            return None
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "text/html" not in content_type.lower():
            return None
        parser = _TextExtractingParser(base_url=final_url)
        try:
            parser.feed(response.text)
        except Exception:
            return None
        text = " ".join(parser.text.split())
        if not text:
            return None
        links = [
            item
            for item in _dedupe_urls(parser.links)
            if _is_url_allowed(item, config.allowed_prefixes)
        ]
        return _WebPage(
            url=final_url,
            title=parser.title.strip() or urlparse(final_url).netloc,
            text=text,
            links=links,
        )


class _TextExtractingParser(HTMLParser):
    """轻量 HTML 正文和链接抽取器。"""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.text_parts: list[str] = []
        self.links: list[str] = []

    @property
    def text(self) -> str:
        """返回抽取后的正文。"""

        return " ".join(self.text_parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        normalized = _normalize_url(urljoin(self._base_url, href))
        if normalized is not None:
            self.links.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title = f"{self.title} {cleaned}".strip()
            return
        self.text_parts.append(cleaned)


def build_web_search_config(raw_config: dict[str, Any], settings: Settings) -> WebSearchConfig:
    """从知识库配置构造联网检索配置。"""

    allowed_prefixes = _normalize_url_list(raw_config.get("allowed_web_prefixes"))
    seed_urls = _normalize_url_list(raw_config.get("web_seed_urls"))
    return WebSearchConfig(
        enabled=raw_config.get("web_enabled") is True,
        allowed_prefixes=allowed_prefixes,
        seed_urls=[item for item in seed_urls if _is_url_allowed(item, allowed_prefixes)],
        topk=_normalize_int(raw_config.get("web_search_topk"), settings.rag_web_search_topk, 1, 10),
        search_provider=settings.rag_web_search_provider,
        search_base_url=settings.rag_web_search_base_url,
        search_api_key=settings.rag_web_search_api_key,
        search_result_limit=_normalize_int(
            raw_config.get("web_search_result_limit"),
            settings.rag_web_search_result_limit,
            1,
            50,
        ),
        max_pages=_normalize_int(
            raw_config.get("web_search_max_pages"),
            settings.rag_web_search_max_pages,
            1,
            20,
        ),
        timeout_s=_normalize_int(
            raw_config.get("web_fetch_timeout_s"),
            settings.rag_web_fetch_timeout_s,
            1,
            30,
        ),
    )


def _build_search_provider(settings: Settings) -> WebSearchProvider:
    """按配置构造联网搜索提供方。"""

    if settings.rag_web_search_provider == "searxng" and settings.rag_web_search_base_url:
        return SearxngSearchProvider(
            base_url=settings.rag_web_search_base_url,
            api_key=settings.rag_web_search_api_key,
        )
    return SeedOnlySearchProvider()


def _build_web_payload(kb_id: str, page: _WebPage, text: str) -> dict[str, Any]:
    """构造符合证据链要求的网页 payload。"""

    digest = sha1(page.url.encode("utf-8")).hexdigest()
    text_digest = sha1(text.encode("utf-8")).hexdigest()
    return {
        "contract_version": "0.1",
        "kb_id": kb_id,
        "doc_id": f"web_{digest[:16]}",
        "doc_name": page.title,
        "doc_version": None,
        "published_at": None,
        "published_at_ts": None,
        "page_start": None,
        "page_end": None,
        "section_path": page.title,
        "chunk_id": f"web_{digest[:16]}_{text_digest[:12]}",
        "chunk_index": 0,
        "text": text,
        "source_type": "web",
        "source_uri": page.url,
        "hash": text_digest,
        "tokens": None,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_url_list(value: object) -> list[str]:
    """归一化 URL 列表并去重。"""

    if not isinstance(value, list):
        return []
    return _dedupe_urls(str(item).strip() for item in value if str(item).strip())


def _normalize_url(url: str) -> str | None:
    """归一化并初步校验 URL。"""

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if _is_blocked_host(parsed.hostname):
        return None
    return parsed.geturl().split("#", 1)[0]


def _is_url_allowed(url: str, allowed_prefixes: list[str]) -> bool:
    """判断 URL 是否落在知识库授权范围内。"""

    normalized = _normalize_url(url)
    if normalized is None:
        return False
    target = urlparse(normalized)
    for prefix in allowed_prefixes:
        normalized_prefix = _normalize_url(prefix)
        if normalized_prefix is None:
            continue
        allowed = urlparse(normalized_prefix)
        if _url_origin(target) != _url_origin(allowed):
            continue
        if _is_path_within_prefix(target.path, allowed.path):
            return True
    return False


def _url_origin(parsed) -> tuple[str, str, int | None]:
    """提取 URL 源，避免字符串前缀误授权相似域名。"""

    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme, str(parsed.hostname or "").lower().strip("[]"), port


def _is_path_within_prefix(path: str, prefix_path: str) -> bool:
    """校验网页路径是否落在授权路径边界内。"""

    normalized_path = path or "/"
    normalized_prefix = prefix_path or "/"
    if normalized_prefix == "/":
        return True
    if normalized_path == normalized_prefix:
        return True
    return normalized_path.startswith(f"{normalized_prefix.rstrip('/')}/")


def _allowed_hosts(allowed_prefixes: list[str]) -> list[str]:
    """从授权前缀中提取搜索站点限定主机。"""

    hosts: list[str] = []
    seen: set[str] = set()
    for prefix in allowed_prefixes:
        parsed = urlparse(prefix)
        hostname = parsed.hostname
        if not hostname:
            continue
        host = hostname.lower().strip("[]")
        if host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts


def _is_blocked_host(hostname: str | None) -> bool:
    """拒绝 localhost、内网 IP 与明显不可公开访问的主机。"""

    if not hostname:
        return True
    lowered = hostname.lower().strip("[]")
    if lowered in {"localhost"} or lowered.endswith(".localhost"):
        return True
    try:
        address = ip_address(lowered)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _dedupe_urls(urls) -> list[str]:
    """按顺序去重 URL。"""

    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = _normalize_url(str(url))
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _score_text(query: str, text: str) -> float:
    """按查询词覆盖率给网页打分。"""

    tokens = _tokenize_query(query)
    if not tokens:
        return 0.0
    lowered = text.lower()
    covered = sum(1 for token in tokens if token in lowered)
    return covered / max(1, len(tokens))


def _tokenize_query(query: str) -> list[str]:
    """拆分联网检索关键词。"""

    cleaned = " ".join(query.strip().lower().split())
    if not cleaned:
        return []
    words = [item for item in cleaned.split() if len(item) > 1]
    if len(words) == 1 and _contains_cjk(words[0]):
        phrases = [
            "计算机科学与工程学院",
            "最新",
            "通知",
            "公告",
            "公示",
            "考务",
            "学工",
            "学院",
        ]
        matched = [item for item in phrases if item in words[0]]
        if matched:
            return matched
    if words:
        return words
    return [char for char in cleaned if char.strip()]


def _contains_cjk(value: str) -> bool:
    """判断文本是否包含中文字符。"""

    return re.search(r"[\u4e00-\u9fff]", value) is not None


def _trim_text(text: str, max_chars: int) -> str:
    """裁剪网页正文，避免单页内容挤占上下文预算。"""

    cleaned = " ".join(text.split())
    return cleaned[:max_chars]


def _normalize_int(value: object, default: int, min_value: int, max_value: int) -> int:
    """归一化整型配置。"""

    if isinstance(value, bool) or not isinstance(value, int):
        candidate = default
    else:
        candidate = value
    if candidate < min_value or candidate > max_value:
        return default
    return candidate
