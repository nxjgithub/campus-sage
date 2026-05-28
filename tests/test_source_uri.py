from app.rag.source_uri import is_official_source_uri


def test_official_source_uri_accepts_http_links() -> None:
    assert is_official_source_uri("https://example.edu/notice") is True


def test_official_source_uri_rejects_demo_placeholder() -> None:
    assert (
        is_official_source_uri("https://www.suse.edu.cn/demo/campus-sage/main.psp")
        is False
    )


def test_official_source_uri_rejects_local_paths() -> None:
    assert is_official_source_uri("data/正式文件/demo.docx") is False
