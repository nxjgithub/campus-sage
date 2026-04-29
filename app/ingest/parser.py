from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.error_codes import ErrorCode
from app.core.errors import AppError

_WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_WORD_NS = _WORD_NAMESPACE["w"]


@dataclass(slots=True)
class ParsedPage:
    """统一的解析片段。"""

    page_number: int | None
    text: str
    section_path: str | None = None


class DocumentParser:
    """文档解析器，按文件类型选择具体解析策略。"""

    def parse(self, path: str | Path) -> list[ParsedPage]:
        """解析文件并返回统一的文本片段列表。"""

        target = Path(path)
        if not target.exists():
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="文件不存在，无法解析",
                detail={"path": str(target)},
                status_code=400,
            )

        extension = target.suffix.lower()
        content = target.read_bytes()

        if extension == ".pdf":
            pages = self._parse_pdf(target, content)
        elif extension == ".docx":
            pages = self._parse_docx(target)
        elif extension in {".html", ".htm"}:
            pages = self._parse_html(content)
        elif extension in {".md", ".txt"}:
            pages = self._parse_text_document(content, extension)
        else:
            raise AppError(
                code=ErrorCode.FILE_TYPE_NOT_ALLOWED,
                message="文件类型不允许",
                detail={"ext": extension.lstrip(".")},
                status_code=400,
            )

        cleaned = self._sanitize_pages(pages)
        if cleaned:
            return cleaned
        raise AppError(
            code=ErrorCode.INGEST_PARSE_FAILED,
            message="未提取到有效文本",
            detail={"path": str(target), "ext": extension.lstrip(".")},
            status_code=400,
        )

    def _parse_pdf(self, path: Path, content: bytes) -> list[ParsedPage]:
        """解析 PDF，保留页码定位。"""

        if not content.startswith(b"%PDF"):
            text = self._decode_text(content)
            return [ParsedPage(page_number=1, text=text)] if text.strip() else []

        reader = self._load_pdf_reader(path)
        table_lines_by_page = self._extract_pdf_table_lines_by_page(path)
        pages: list[ParsedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            table_lines = table_lines_by_page.get(index, [])
            combined = "\n".join(part for part in (text.strip(), "\n".join(table_lines).strip()) if part)
            if combined.strip():
                pages.append(ParsedPage(page_number=index, text=combined))
        return pages

    def _parse_docx(self, path: Path) -> list[ParsedPage]:
        """解析 DOCX，并尽量保留标题层级。"""

        try:
            with ZipFile(path) as archive:
                xml_content = archive.read("word/document.xml")
        except KeyError as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="DOCX 缺少正文内容，无法解析",
                detail={"path": str(path)},
                status_code=400,
            ) from exc
        except BadZipFile as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="DOCX 文件损坏，无法解析",
                detail={"path": str(path)},
                status_code=400,
            ) from exc

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="DOCX 内容格式异常，无法解析",
                detail={"path": str(path)},
                status_code=400,
            ) from exc

        body = root.find(".//w:body", _WORD_NAMESPACE)
        if body is None:
            return []

        blocks: list[tuple[int | None, str]] = []
        for child in body:
            if child.tag == self._word_tag("p"):
                text = self._extract_docx_paragraph_text(child)
                if text:
                    blocks.append((self._extract_docx_heading_level(child), text))
                continue
            if child.tag == self._word_tag("tbl"):
                blocks.extend((None, line) for line in self._extract_docx_table_lines(child))
        return self._build_structured_pages(blocks)

    def _parse_html(self, content: bytes) -> list[ParsedPage]:
        """解析 HTML，并过滤脚本与样式。"""

        parser = _StructuredHtmlParser()
        parser.feed(self._decode_text(content))
        parser.close()
        return self._build_structured_pages(parser.blocks)

    def _parse_text_document(self, content: bytes, extension: str) -> list[ParsedPage]:
        """解析 Markdown 或纯文本。"""

        text = self._decode_text(content)
        if extension == ".md":
            return self._parse_markdown(text)
        return [ParsedPage(page_number=None, text=text)]

    def _parse_markdown(self, text: str) -> list[ParsedPage]:
        """解析 Markdown 标题层级。"""

        blocks: list[tuple[int | None, str]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading_level = self._detect_markdown_heading_level(line)
            if heading_level is not None:
                blocks.append((heading_level, line[heading_level + 1 :].strip()))
                continue
            blocks.append((None, line))
        return self._build_structured_pages(blocks)

    def _build_structured_pages(self, blocks: list[tuple[int | None, str]]) -> list[ParsedPage]:
        """根据标题层级构建统一的引用片段。"""

        pages: list[ParsedPage] = []
        heading_stack: list[str] = []
        body_lines: list[str] = []

        def flush() -> None:
            text = "\n".join(line for line in body_lines if line.strip()).strip()
            if not text:
                body_lines.clear()
                return
            section_path = "/".join(heading_stack) if heading_stack else None
            if section_path and len(body_lines) == 1 and body_lines[0] == heading_stack[-1]:
                body_lines.clear()
                return
            pages.append(ParsedPage(page_number=None, text=text, section_path=section_path))
            body_lines.clear()

        for heading_level, text in blocks:
            normalized = self._normalize_line(text)
            if not normalized:
                continue
            if heading_level is None:
                body_lines.append(normalized)
                continue
            flush()
            while len(heading_stack) >= heading_level:
                heading_stack.pop()
            heading_stack.append(normalized)
            body_lines.append(normalized)

        flush()
        return pages

    def _sanitize_pages(self, pages: list[ParsedPage]) -> list[ParsedPage]:
        """移除空白片段并统一裁剪文本。"""

        cleaned: list[ParsedPage] = []
        for page in pages:
            if self._is_glyph_garbage(page.text):
                continue
            text = self._normalize_line(page.text)
            if not text:
                continue
            section_path = self._normalize_line(page.section_path) if page.section_path else None
            cleaned.append(
                ParsedPage(
                    page_number=page.page_number,
                    text=text,
                    section_path=section_path,
                )
            )
        return cleaned

    def _decode_text(self, content: bytes) -> str:
        """容错解码文本。"""

        for encoding in ("utf-8", "utf-16", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _load_pdf_reader(self, path: Path) -> Any:
        """加载 PDF 解析器。"""

        try:
            from pypdf import PdfReader  # type: ignore

            return PdfReader(path)
        except Exception as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="缺少 PDF 解析依赖，无法解析 PDF",
                detail={"path": str(path), "error": str(exc)},
                status_code=400,
            ) from exc

    def _extract_pdf_table_lines_by_page(self, path: Path) -> dict[int, list[str]]:
        """使用可选依赖抽取 PDF 表格，失败时退回普通文本解析。"""

        try:
            import pdfplumber  # type: ignore
        except ImportError:
            return {}

        table_lines_by_page: dict[int, list[str]] = {}
        try:
            with pdfplumber.open(path) as document:
                for page_index, page in enumerate(document.pages, start=1):
                    lines: list[str] = []
                    for table in page.extract_tables() or []:
                        for row in table:
                            values = [self._normalize_table_cell(cell) for cell in row]
                            values = [value for value in values if value]
                            if len(values) >= 2:
                                lines.append(" | ".join(values))
                    if lines:
                        table_lines_by_page[page_index] = self._dedupe_adjacent_lines(lines)
        except Exception:
            return {}
        return table_lines_by_page

    def _extract_docx_paragraph_text(self, paragraph: ET.Element) -> str:
        """提取 DOCX 段落文本。"""

        texts = [node.text or "" for node in paragraph.findall(".//w:t", _WORD_NAMESPACE)]
        return self._normalize_line("".join(texts))

    def _extract_docx_table_lines(self, table: ET.Element) -> list[str]:
        """提取 DOCX 表格行，使用 Markdown 风格保留列关系。"""

        lines: list[str] = []
        for row in table.findall("./w:tr", _WORD_NAMESPACE):
            values = [self._extract_docx_cell_text(cell) for cell in row.findall("./w:tc", _WORD_NAMESPACE)]
            values = [value for value in values if value]
            if len(values) >= 2:
                lines.append(" | ".join(values))
        return self._dedupe_adjacent_lines(lines)

    def _extract_docx_cell_text(self, cell: ET.Element) -> str:
        """提取 DOCX 单元格文本，避免表格内容被拆成孤立短行。"""

        paragraphs = [
            self._extract_docx_paragraph_text(paragraph)
            for paragraph in cell.findall(".//w:p", _WORD_NAMESPACE)
        ]
        return self._normalize_table_cell(" ".join(paragraph for paragraph in paragraphs if paragraph))

    def _extract_docx_heading_level(self, paragraph: ET.Element) -> int | None:
        """识别 DOCX 段落的标题级别。"""

        style = paragraph.find("./w:pPr/w:pStyle", _WORD_NAMESPACE)
        style_value = style.attrib.get(f"{{{_WORD_NAMESPACE['w']}}}val", "") if style is not None else ""
        style_lower = style_value.lower()
        if style_lower.startswith("heading"):
            level_text = style_lower.replace("heading", "", 1).strip()
            if level_text.isdigit():
                return max(1, int(level_text))
        return None

    def _detect_markdown_heading_level(self, line: str) -> int | None:
        """识别 Markdown 标题。"""

        if not line.startswith("#"):
            return None
        marker = line.split(" ", 1)[0]
        if set(marker) != {"#"}:
            return None
        if len(marker) > 6 or len(line) == len(marker):
            return None
        return len(marker)

    def _normalize_line(self, text: str | None) -> str:
        """统一压缩行内多余空白。"""

        if text is None:
            return ""
        return "\n".join(part.strip() for part in text.splitlines() if part.strip()).strip()

    def _normalize_table_cell(self, text: str | None) -> str:
        """统一表格单元格文本，保持同一单元格内容在一行内。"""

        return re.sub(r"\s+", " ", text or "").strip()

    def _dedupe_adjacent_lines(self, lines: list[str]) -> list[str]:
        """去除相邻重复行，降低抽表和正文文本重复带来的噪声。"""

        deduped: list[str] = []
        for line in lines:
            if deduped and deduped[-1] == line:
                continue
            deduped.append(line)
        return deduped

    def _is_glyph_garbage(self, text: str) -> bool:
        """识别 PDF 字体映射失败产生的 /Gxx 占位乱码。"""

        glyph_tokens = re.findall(r"/G[0-9A-Fa-f]{2,}", text or "")
        return len(glyph_tokens) >= 20

    def _word_tag(self, name: str) -> str:
        """构造 WordprocessingML 命名空间标签。"""

        return f"{{{_WORD_NS}}}{name}"


class _StructuredHtmlParser(HTMLParser):
    """HTML 结构化提取器。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[int | None, str]] = []
        self._current_tag: str | None = None
        self._current_text: list[str] = []
        self._skip_depth = 0
        self._table_depth = 0
        self._row_cells: list[str] = []
        self._cell_text: list[str] = []
        self._in_table_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理开始标签。"""

        tag_lower = tag.lower()
        if tag_lower in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_lower == "table":
            self._flush()
            self._table_depth += 1
            return
        if self._table_depth:
            if tag_lower == "tr":
                self._row_cells = []
                return
            if tag_lower in {"td", "th"}:
                self._cell_text = []
                self._in_table_cell = True
                return
            return
        if tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}:
            self._flush()
            self._current_tag = tag_lower

    def handle_endtag(self, tag: str) -> None:
        """处理结束标签。"""

        tag_lower = tag.lower()
        if tag_lower in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._table_depth:
            if tag_lower in {"td", "th"} and self._in_table_cell:
                text = self._normalize_text(" ".join(self._cell_text))
                if text:
                    self._row_cells.append(text)
                self._cell_text = []
                self._in_table_cell = False
                return
            if tag_lower == "tr":
                if len(self._row_cells) >= 2:
                    self.blocks.append((None, " | ".join(self._row_cells)))
                self._row_cells = []
                return
            if tag_lower == "table":
                self._table_depth = max(0, self._table_depth - 1)
                return
            return
        if self._current_tag == tag_lower:
            self._flush()
            self._current_tag = None

    def handle_data(self, data: str) -> None:
        """收集正文文本。"""

        if self._skip_depth:
            return
        if self._table_depth and self._in_table_cell:
            self._cell_text.append(data)
            return
        self._current_text.append(data)

    def close(self) -> None:
        """结束解析时冲刷残留文本。"""

        self._flush()
        super().close()

    def _flush(self) -> None:
        text = self._normalize_text(" ".join(part.strip() for part in self._current_text if part.strip()))
        self._current_text.clear()
        if not text:
            return
        heading_level = None
        if self._current_tag and self._current_tag.startswith("h") and self._current_tag[1:].isdigit():
            heading_level = int(self._current_tag[1:])
        self.blocks.append((heading_level, text))

    def _normalize_text(self, text: str) -> str:
        """统一 HTML 抽取出的行内空白。"""

        return re.sub(r"\s+", " ", text or "").strip()
