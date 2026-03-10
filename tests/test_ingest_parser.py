from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from app.ingest.parser import DocumentParser


def test_parse_markdown_keeps_heading_path(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "demo.md"
    file_path.write_text("# 教务管理\n## 补考申请\n学生需提交申请材料。", encoding="utf-8")

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path == "教务管理/补考申请"
    assert "学生需提交申请材料" in pages[0].text


def test_parse_html_extracts_heading_and_text(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "demo.html"
    file_path.write_text(
        "<html><body><h1>考试管理</h1><p>补考申请需在规定时间内提交。</p></body></html>",
        encoding="utf-8",
    )

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path == "考试管理"
    assert "补考申请需在规定时间内提交" in pages[0].text


def test_parse_docx_extracts_heading_and_body(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "demo.docx"
    file_path.write_bytes(
        _build_docx_bytes(
            [
                (1, "考试管理"),
                (None, "补考申请需在规定时间内提交。"),
            ]
        )
    )

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path == "考试管理"
    assert "补考申请需在规定时间内提交" in pages[0].text


def test_parse_txt_returns_plain_text(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "demo.txt"
    file_path.write_text("普通文本内容", encoding="utf-8")

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path is None
    assert pages[0].text == "普通文本内容"


def _build_docx_bytes(paragraphs: list[tuple[int | None, str]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        body = "".join(_render_docx_paragraph(level, text) for level, text in paragraphs)
        archive.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
  </w:body>
</w:document>""",
        )
    return buffer.getvalue()


def _render_docx_paragraph(level: int | None, text: str) -> str:
    if level is None:
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
    return (
        "<w:p>"
        f"<w:pPr><w:pStyle w:val=\"Heading{level}\" /></w:pPr>"
        f"<w:r><w:t>{text}</w:t></w:r>"
        "</w:p>"
    )
