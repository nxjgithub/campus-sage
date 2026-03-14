from __future__ import annotations

from pathlib import Path

from scripts.bootstrap_suse_public_kb import (
    CrawledRecord,
    SavedPage,
    build_attachment_title_map,
    infer_attachment_name_from_body,
    is_ingestable_file,
    is_opaque_attachment_name,
    is_list_page,
    parse_saved_page,
    resolve_crawl_dir,
)


def test_resolve_crawl_dir_picks_latest_directory(monkeypatch, tmp_path: Path) -> None:
    crawl_root = tmp_path / "data" / "crawl"
    older = crawl_root / "suse_public_20260314_010000"
    newer = crawl_root / "suse_public_20260314_020000"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    monkeypatch.setattr("scripts.bootstrap_suse_public_kb.ROOT_DIR", tmp_path)

    assert resolve_crawl_dir(None) == newer


def test_parse_saved_page_extracts_title_source_and_body(monkeypatch, tmp_path: Path) -> None:
    page_file = tmp_path / "sample.md"
    page_file.write_text(
        "\n".join(
            [
                "# 关于开展奖学金评选工作的通知",
                "",
                "- 来源：https://xsc.suse.edu.cn/2026/0314/demo/page.htm",
                "- 抓取时间：2026-03-14T08:00:00+00:00",
                "",
                "## 正文",
                "",
                "各学院：",
                "现将奖学金评选工作安排如下。",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.bootstrap_suse_public_kb.ROOT_DIR", tmp_path)

    page = parse_saved_page(
        CrawledRecord(
            kind="page",
            site_code="xsc",
            source_uri="https://fallback.example/page.htm",
            title="fallback",
            local_path="sample.md",
            content_type="text/html",
            text_length=18,
            crawled_at="2026-03-14T08:00:00+00:00",
        )
    )

    assert page.title == "关于开展奖学金评选工作的通知"
    assert page.source_uri == "https://xsc.suse.edu.cn/2026/0314/demo/page.htm"
    assert "奖学金评选工作安排如下" in page.body


def test_is_list_page_detects_notice_lines() -> None:
    record = CrawledRecord(
        kind="page",
        site_code="yjs",
        source_uri="https://yjs.suse.edu.cn/gsgg/list.htm",
        title="公示公告",
        local_path="unused.md",
        content_type="text/html",
        text_length=120,
        crawled_at="2026-03-14T08:00:00+00:00",
    )
    page = parse_saved_page_from_text(
        record,
        "\n".join(
            [
                "2026年硕士研究生招生复试相关问题解答 | 2026-03-01",
                "2026年研考国家线发布 | 2026-02-28",
                "2026年研究生招生考试初试成绩查询通知 | 2026-02-26",
                "关于提交复试资格审核材料的通知 | 2026-02-20",
                "研究生复试诚信提醒 | 2026-02-18",
            ]
        ),
    )

    assert is_list_page(page) is True


def test_infer_attachment_name_from_body_returns_unique_match() -> None:
    body = "\n".join(
        [
            "经审核，现将结果予以公示。",
            "四川轻化工大学大学生创新创业协会2024-2025年度先进个人评优名单.docx",
        ]
    )

    assert (
        infer_attachment_name_from_body(
            body,
            "https://jwc.suse.edu.cn/_upload/article/files/demo.docx",
        )
        == "四川轻化工大学大学生创新创业协会2024-2025年度先进个人评优名单.docx"
    )


def test_build_attachment_title_map_uses_site_page_candidates(monkeypatch, tmp_path: Path) -> None:
    page_file = tmp_path / "page.md"
    page_file.write_text(
        "\n".join(
            [
                "# 通知公告",
                "",
                "- 来源：https://jwc.suse.edu.cn/tzgg/list.htm",
                "",
                "## 正文",
                "",
                "经审核，现将结果予以公示。",
                "四川轻化工大学大学生创新创业协会2024-2025年度先进个人评优名单.docx",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.bootstrap_suse_public_kb.ROOT_DIR", tmp_path)
    records = [
        CrawledRecord(
            kind="page",
            site_code="jwc",
            source_uri="https://jwc.suse.edu.cn/tzgg/list.htm",
            title="通知公告",
            local_path="page.md",
            content_type="text/html",
            text_length=100,
            crawled_at="2026-03-14T08:00:00+00:00",
        ),
        CrawledRecord(
            kind="attachment",
            site_code="jwc",
            source_uri="https://jwc.suse.edu.cn/_upload/article/files/demo.docx",
            title="demo.docx",
            local_path="attachment.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            text_length=None,
            crawled_at="2026-03-14T08:00:00+00:00",
        ),
    ]

    result = build_attachment_title_map(records)

    assert result == {
        "https://jwc.suse.edu.cn/_upload/article/files/demo.docx": "四川轻化工大学大学生创新创业协会2024-2025年度先进个人评优名单.docx"
    }


def test_is_opaque_attachment_name_detects_uuid_like_filenames() -> None:
    assert is_opaque_attachment_name("119976f1-5c52-422b-aa73-f3a8fd21909c.docx") is True
    assert is_opaque_attachment_name("附件_四川轻化工大学2026年精密设备维修服务_响应文件格式.docx") is False


def test_is_ingestable_file_accepts_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "demo.md"
    file_path.write_text("# 标题\n\n这是可解析的 Markdown 正文。", encoding="utf-8")

    assert is_ingestable_file(file_path) is True


def parse_saved_page_from_text(record: CrawledRecord, body: str) -> SavedPage:
    """构造仅用于测试的临时页面对象。"""

    return SavedPage(
        site_code=record.site_code,
        title=record.title,
        source_uri=record.source_uri,
        body=body,
        local_path=Path("unused.md"),
    )
