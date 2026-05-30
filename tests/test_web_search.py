from app.core.settings import Settings
from app.rag.web_search import (
    SearxngSearchProvider,
    WebEvidenceRetriever,
    _is_url_allowed,
    build_web_search_config,
)


def test_web_search_config_rejects_localhost_and_outside_seed() -> None:
    settings = Settings(_env_file=None)

    config = build_web_search_config(
        {
            "web_enabled": True,
            "allowed_web_prefixes": [
                "http://127.0.0.1:8000/",
                "https://jwc.example.edu/",
            ],
            "web_seed_urls": [
                "https://jwc.example.edu/list.html",
                "https://evil.example.com/list.html",
            ],
        },
        settings,
    )

    assert config.enabled is True
    assert config.allowed_prefixes == ["https://jwc.example.edu/"]
    assert config.seed_urls == ["https://jwc.example.edu/list.html"]


def test_url_allowlist_requires_matching_origin_and_path_boundary() -> None:
    """授权前缀不能放行相似域名或相似路径。"""

    assert _is_url_allowed(
        "https://jwc.example.edu/notices/2026.html",
        ["https://jwc.example.edu/notices"],
    )
    assert not _is_url_allowed(
        "https://jwc.example.edu.evil.test/notices/2026.html",
        ["https://jwc.example.edu"],
    )
    assert not _is_url_allowed(
        "https://jwc.example.edu/notices-archive/2026.html",
        ["https://jwc.example.edu/notices"],
    )


def test_searxng_search_provider_filters_to_allowed_prefix(monkeypatch) -> None:
    """搜索结果必须经过授权前缀过滤。"""

    captured: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {
                        "title": "授权通知",
                        "url": "https://jsj.example.edu/xgtz/info/1.htm",
                        "content": "通知摘要",
                    },
                    {
                        "title": "越界结果",
                        "url": "https://evil.example.com/info/1.htm",
                    },
                ]
            }

    def fake_get(url, params, headers, timeout, trust_env):
        del headers, timeout, trust_env
        captured["url"] = url
        captured["query"] = params["q"]
        return _Response()

    monkeypatch.setattr("app.rag.web_search.httpx.get", fake_get)

    provider = SearxngSearchProvider("http://127.0.0.1:8080")
    results = provider.search(
        query="最新 通知",
        allowed_prefixes=["https://jsj.example.edu/xgtz/"],
        limit=5,
        timeout_s=3,
    )

    assert captured["url"] == "http://127.0.0.1:8080/search"
    assert captured["query"] == "site:jsj.example.edu 最新 通知"
    assert [item.url for item in results] == ["https://jsj.example.edu/xgtz/info/1.htm"]


def test_web_retriever_uses_search_results_before_seed_urls(monkeypatch) -> None:
    """配置搜索提供方后应先抓搜索结果原网页。"""

    settings = Settings(
        _env_file=None,
        rag_web_search_provider="searxng",
        rag_web_search_base_url="http://127.0.0.1:8080",
        rag_web_search_max_pages=3,
    )
    config = build_web_search_config(
        {
            "web_enabled": True,
            "allowed_web_prefixes": ["https://jsj.example.edu/"],
            "web_seed_urls": ["https://jsj.example.edu/xgtz/list.htm"],
            "web_search_topk": 2,
        },
        settings,
    )

    class _Response:
        def __init__(self, url: str, text: str = "", payload: dict | None = None) -> None:
            self.status_code = 200
            self.url = url
            self.text = text
            self._payload = payload
            self.headers = {"content-type": "text/html"}

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if str(url).endswith("/search"):
            return _Response(
                str(url),
                payload={
                    "results": [
                        {
                            "title": "最新通知",
                            "url": "https://jsj.example.edu/xgtz/info/2026.htm",
                            "content": "最新 通知",
                        }
                    ]
                },
            )
        return _Response(
            str(url),
            text=(
                "<html><head><title>最新通知</title></head>"
                "<body>计算机科学与工程学院发布最新通知，学生按要求办理。</body></html>"
            ),
        )

    monkeypatch.setattr("app.rag.web_search.httpx.get", fake_get)

    hits = WebEvidenceRetriever(settings).retrieve(
        kb_id="kb_web",
        kb_name="联网知识库",
        question="请查一下计算机科学与工程学院官网最新通知有哪些？",
        query="计算机科学与工程学院 最新 通知",
        config=config,
    )

    assert hits
    assert hits[0].payload["source_type"] == "web"
    assert hits[0].payload["source_uri"] == "https://jsj.example.edu/xgtz/info/2026.htm"


def test_web_retriever_falls_back_to_seed_when_search_returns_empty(monkeypatch) -> None:
    """搜索引擎触发 CAPTCHA 等故障时仍应抓取授权入口页。"""

    settings = Settings(
        _env_file=None,
        rag_web_search_provider="searxng",
        rag_web_search_base_url="http://127.0.0.1:8080",
        rag_web_search_max_pages=1,
    )
    config = build_web_search_config(
        {
            "web_enabled": True,
            "allowed_web_prefixes": ["https://jsj.example.edu/"],
            "web_seed_urls": ["https://jsj.example.edu/xgtz/list.htm"],
            "web_search_topk": 1,
        },
        settings,
    )

    class _Response:
        def __init__(self, url: str, text: str = "", payload: dict | None = None) -> None:
            self.status_code = 200
            self.url = url
            self.text = text
            self._payload = payload
            self.headers = {"content-type": "text/html"}

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if str(url).endswith("/search"):
            return _Response(str(url), payload={"results": []})
        return _Response(
            str(url),
            text=(
                "<html><head><title>学院动态</title></head>"
                "<body>计算机科学与工程学院发布学院动态，学生可以查看通知。</body></html>"
            ),
        )

    monkeypatch.setattr("app.rag.web_search.httpx.get", fake_get)

    hits = WebEvidenceRetriever(settings).retrieve(
        kb_id="kb_web",
        kb_name="联网知识库",
        question="学院动态有哪些？",
        query="学院动态",
        config=config,
    )

    assert len(hits) == 1
    assert hits[0].payload["source_type"] == "web"
    assert hits[0].payload["source_uri"] == "https://jsj.example.edu/xgtz/list.htm"
