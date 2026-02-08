from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.error_codes import ErrorCode
from app.core.errors import AppError


@dataclass(slots=True)
class ParsedPage:
    page_number: int | None
    text: str


class DocumentParser:
    """文档解析器（MVP 先做容错解析）。"""

    def parse(self, path: str | Path) -> list[ParsedPage]:
        """解析文件并返回按页组织的文本。"""

        target = Path(path)
        if not target.exists():
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="文件不存在，无法解析",
                detail={"path": str(target)},
                status_code=400,
            )

        content = target.read_bytes()
        if self._is_pdf(target, content):
            pages = self._parse_pdf(target, content)
            if pages:
                return pages

        text = self._decode_text(content)
        if not text.strip():
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="未提取到有效文本",
                detail={"path": str(target)},
                status_code=400,
            )
        return [ParsedPage(page_number=1, text=text)]

    def _decode_text(self, content: bytes) -> str:
        """容错解码文本（无解析器时的降级策略）。"""

        for encoding in ("utf-8", "utf-16", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _is_pdf(self, path: Path, content: bytes) -> bool:
        """判断是否为 PDF。"""

        if path.suffix.lower() == ".pdf":
            return content.startswith(b"%PDF")
        return content.startswith(b"%PDF")

    def _parse_pdf(self, path: Path, content: bytes) -> list[ParsedPage]:
        """解析 PDF（需要 pypdf 支持）。"""

        reader = self._load_pdf_reader(path, content)
        pages: list[ParsedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(ParsedPage(page_number=index, text=text))
        return pages

    def _load_pdf_reader(self, path: Path, content: bytes) -> Any:
        """加载 PDF 解析器。"""

        try:
            from pypdf import PdfReader  # type: ignore

            return PdfReader(path)
        except Exception:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="缺少 PDF 解析依赖，无法解析 PDF",
                detail={"path": str(path)},
                status_code=400,
            )
