from __future__ import annotations

import io
from pathlib import Path
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.core.errors import AppError
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


def test_parse_html_preserves_table_rows(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "table.html"
    file_path.write_text(
        """
        <html><body>
          <h1>调剂专业</h1>
          <table>
            <tr><th>学院</th><th>专业</th><th>联系人</th></tr>
            <tr><td>计算机学院</td><td>电子信息</td><td>张老师</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert "学院 | 专业 | 联系人" in pages[0].text
    assert "计算机学院 | 电子信息 | 张老师" in pages[0].text


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


def test_parse_docx_preserves_table_rows(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "table.docx"
    file_path.write_bytes(
        _build_docx_bytes_from_body(
            "".join(
                [
                    _render_docx_paragraph(1, "招生专业"),
                    _render_docx_table(
                        [
                            ["学院", "专业", "学习形式"],
                            ["计算机学院", "电子信息", "全日制"],
                        ]
                    ),
                ]
            )
        )
    )

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path == "招生专业"
    assert "学院 | 专业 | 学习形式" in pages[0].text
    assert "计算机学院 | 电子信息 | 全日制" in pages[0].text


def test_parse_pdf_appends_optional_pdfplumber_table_rows(monkeypatch, tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "table.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    class FakePdfPage:
        def extract_text(self) -> str:
            return "招生专业说明"

    class FakePdfReader:
        pages = [FakePdfPage()]

    class FakePlumberPage:
        def extract_tables(self) -> list[list[list[str]]]:
            return [[["学院", "专业"], ["计算机学院", "电子信息"]]]

    class FakePlumberDocument:
        pages = [FakePlumberPage()]

        def __enter__(self) -> "FakePlumberDocument":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    fake_pdfplumber = SimpleNamespace(open=lambda _path: FakePlumberDocument())
    monkeypatch.setitem(sys.modules, "pdfplumber", fake_pdfplumber)
    monkeypatch.setattr(parser, "_load_pdf_reader", lambda _path: FakePdfReader())

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert "招生专业说明" in pages[0].text
    assert "学院 | 专业" in pages[0].text
    assert "计算机学院 | 电子信息" in pages[0].text


def test_parse_pdf_rejects_glyph_garbage(monkeypatch, tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "garbage.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")

    class FakePdfPage:
        def extract_text(self) -> str:
            return " ".join(f"/G{index:02X}" for index in range(40))

    class FakePdfReader:
        pages = [FakePdfPage()]

    monkeypatch.setattr(parser, "_load_pdf_reader", lambda _path: FakePdfReader())

    with pytest.raises(AppError):
        parser.parse(file_path)


def test_parse_txt_returns_plain_text(tmp_path: Path) -> None:
    parser = DocumentParser()
    file_path = tmp_path / "demo.txt"
    file_path.write_text("普通文本内容", encoding="utf-8")

    pages = parser.parse(file_path)

    assert len(pages) == 1
    assert pages[0].section_path is None
    assert pages[0].text == "普通文本内容"


def _build_docx_bytes(paragraphs: list[tuple[int | None, str]]) -> bytes:
    return _build_docx_bytes_from_body("".join(_render_docx_paragraph(level, text) for level, text in paragraphs))


def _build_docx_bytes_from_body(body: str) -> bytes:
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


def _render_docx_table(rows: list[list[str]]) -> str:
    rendered_rows = []
    for row in rows:
        cells = "".join(f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row)
        rendered_rows.append(f"<w:tr>{cells}</w:tr>")
    return f"<w:tbl>{''.join(rendered_rows)}</w:tbl>"
