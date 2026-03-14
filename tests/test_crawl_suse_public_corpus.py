from __future__ import annotations

from scripts.crawl_suse_public_corpus import (
    extract_primary_text,
    is_attachment_url,
    normalize_url,
    should_visit_page,
)


def test_normalize_url_resolves_relative_link() -> None:
    result = normalize_url("/2026/0314/c61a1/page.htm#frag", base_url="https://www.suse.edu.cn/61/list.htm")

    assert result == "https://www.suse.edu.cn/2026/0314/c61a1/page.htm"


def test_normalize_url_rejects_non_http_link() -> None:
    assert normalize_url("javascript:void(0)", base_url="https://www.suse.edu.cn/") is None
    assert normalize_url("mailto:test@example.com", base_url="https://www.suse.edu.cn/") is None


def test_should_visit_page_rejects_static_assets() -> None:
    assert should_visit_page("https://www.suse.edu.cn/61/list.htm", allowed_host="www.suse.edu.cn") is True
    assert should_visit_page("https://www.suse.edu.cn/_css/_system/system.css", allowed_host="www.suse.edu.cn") is False
    assert should_visit_page("https://other.example.com/page.htm", allowed_host="www.suse.edu.cn") is False


def test_is_attachment_url_matches_supported_extensions() -> None:
    assert is_attachment_url("https://www.suse.edu.cn/file/test.pdf") is True
    assert is_attachment_url("https://www.suse.edu.cn/file/test.docx") is True
    assert is_attachment_url("https://www.suse.edu.cn/2026/0314/c61a1/page.htm") is False


def test_extract_primary_text_prefers_news_list_fragment() -> None:
    html = """
    <html><body>
    <div class="nav">首页 通知公告</div>
    <div class="col_news_list listcon">
      <ul class="news_list list2">
        <li class="news n1 clearfix">
          <span class="news_title"><a href="/2026/0301/c1/page.htm" title="2026年硕士研究生招生及复试相关问题解答">2026年硕士研究生招生及复试相关问题解答</a></span>
          <span class="news_meta">2026-03-01</span>
        </li>
      </ul>
    </div>
    <div class="footer">Copyright</div>
    </body></html>
    """

    text = extract_primary_text(html, primary_fragment='<ul class="news_list list2"><li class="news n1 clearfix"><span class="news_title"><a href="/2026/0301/c1/page.htm" title="2026年硕士研究生招生及复试相关问题解答">2026年硕士研究生招生及复试相关问题解答</a></span><span class="news_meta">2026-03-01</span></li></ul>')

    assert text == "2026年硕士研究生招生及复试相关问题解答 | 2026-03-01"
