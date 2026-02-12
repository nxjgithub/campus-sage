from __future__ import annotations

from dataclasses import dataclass

from app.ingest.parser import ParsedPage


@dataclass(slots=True)
class Chunk:
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None


class Chunker:
    """文本切分器（按字符长度切分）。"""

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = max(1, chunk_size)
        self._chunk_overlap = max(0, min(chunk_overlap, self._chunk_size - 1))

    def build(self, pages: list[ParsedPage]) -> list[Chunk]:
        """构建分块列表。"""

        chunks: list[Chunk] = []
        chunk_index = 0
        for page in pages:
            section_path = self._extract_section_path(page.text)
            for text in self._split_text(page.text):
                chunks.append(
                    Chunk(
                        chunk_index=chunk_index,
                        text=text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_path=section_path,
                    )
                )
                chunk_index += 1
        return chunks

    def _split_text(self, text: str) -> list[str]:
        """按 chunk_size + overlap 切分文本。"""

        cleaned = text.strip()
        if not cleaned:
            return []
        size = self._chunk_size
        overlap = self._chunk_overlap
        result: list[str] = []
        start = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + size)
            result.append(cleaned[start:end])
            if end == len(cleaned):
                break
            start = max(0, end - overlap)
        return result

    def _extract_section_path(self, text: str) -> str | None:
        """从页面文本中提取章节标题（启发式）。"""

        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if self._is_heading(line):
                return line[:100]
        return None

    def _is_heading(self, line: str) -> bool:
        """判断是否为章节标题（简单规则）。"""

        if len(line) > 60:
            return False
        prefixes = ("第", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")
        if line.startswith(prefixes):
            return True
        for marker in ("章", "节"):
            if line.startswith("第") and marker in line:
                return True
        if line[:1].isdigit() and (". " in line or "、" in line):
            return True
        return False
