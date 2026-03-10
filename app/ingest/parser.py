from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.error_codes import ErrorCode
from app.core.errors import AppError

_WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


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
        pages: list[ParsedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(ParsedPage(page_number=index, text=text))
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

        blocks: list[tuple[int | None, str]] = []
        for paragraph in root.findall(".//w:body/w:p", _WORD_NAMESPACE):
            text = self._extract_docx_paragraph_text(paragraph)
            if not text:
                continue
            blocks.append((self._extract_docx_heading_level(paragraph), text))
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

    def _extract_docx_paragraph_text(self, paragraph: ET.Element) -> str:
        """提取 DOCX 段落文本。"""

        texts = [node.text or "" for node in paragraph.findall(".//w:t", _WORD_NAMESPACE)]
        return self._normalize_line("".join(texts))

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


class _StructuredHtmlParser(HTMLParser):
    """HTML 结构化提取器。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[int | None, str]] = []
        self._current_tag: str | None = None
        self._current_text: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理开始标签。"""

        tag_lower = tag.lower()
        if tag_lower in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
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
        if self._current_tag == tag_lower:
            self._flush()
            self._current_tag = None

    def handle_data(self, data: str) -> None:
        """收集正文文本。"""

        if self._skip_depth:
            return
        self._current_text.append(data)

    def close(self) -> None:
        """结束解析时冲刷残留文本。"""

        self._flush()
        super().close()

    def _flush(self) -> None:
        text = " ".join(part.strip() for part in self._current_text if part.strip()).strip()
        self._current_text.clear()
        if not text:
            return
        heading_level = None
        if self._current_tag and self._current_tag.startswith("h") and self._current_tag[1:].isdigit():
            heading_level = int(self._current_tag[1:])
        self.blocks.append((heading_level, text))
