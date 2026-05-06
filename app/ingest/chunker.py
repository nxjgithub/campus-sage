from __future__ import annotations

from dataclasses import dataclass
import re

from app.ingest.parser import ParsedPage


@dataclass(slots=True)
class Chunk:
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    metadata: dict[str, object] | None = None


@dataclass(slots=True)
class _Section:
    """页内小节切分结果。"""

    text: str
    section_path: str | None


class Chunker:
    """文本切分器（优先按标题、段落和句子边界切分）。"""

    _SECTION_PREFIXES = (
        "一、",
        "二、",
        "三、",
        "四、",
        "五、",
        "六、",
        "七、",
        "八、",
        "九、",
        "十、",
        "十一、",
        "十二、",
    )
    _CHINESE_NUMBER_PATTERN = "[一二三四五六七八九十]+"
    _DOCUMENT_TITLE_SUFFIXES = (
        "通知",
        "公告",
        "通告",
        "方案",
        "办法",
        "指南",
        "说明",
        "细则",
        "规定",
    )
    _SENTENCE_PATTERN = re.compile(r".+?(?:[。！？!?；;]|$)", re.S)

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = max(1, chunk_size)
        self._chunk_overlap = max(0, min(chunk_overlap, self._chunk_size - 1))
        self._min_chunk_chars = min(
            self._chunk_size,
            min(120, max(40, self._chunk_size // 3)),
        )

    def build(self, pages: list[ParsedPage]) -> list[Chunk]:
        """构建分块列表。"""

        chunks: list[Chunk] = []
        chunk_index = 0
        for page in pages:
            for section in self._build_sections(page.text, page.section_path):
                for text in self._split_text(section.text):
                    chunks.append(
                        Chunk(
                            chunk_index=chunk_index,
                            text=text,
                            page_start=page.page_number,
                            page_end=page.page_number,
                            section_path=section.section_path,
                        )
                    )
                    chunk_index += 1
        return chunks

    def _split_text(self, text: str) -> list[str]:
        """按段落和句子边界切分文本，必要时退回字符窗口。"""

        cleaned = self._normalize_text(text)
        if not cleaned:
            return []

        units = self._build_units(cleaned)
        if len(units) == 1 and len(units[0]) <= self._chunk_size:
            return units

        anchor = units[0] if units and self._is_heading(units[0], line_index=0) else None
        chunks: list[str] = []
        current: list[str] = []

        for unit in units:
            if not current:
                current.append(unit)
                continue
            candidate = self._join_units([*current, unit])
            if len(candidate) <= self._chunk_size:
                current.append(unit)
                continue
            if (
                len(self._join_units(current)) < self._min_chunk_chars
                and len(candidate) <= self._chunk_size + self._chunk_overlap
            ):
                current.append(unit)
                continue
            self._append_chunk(chunks, current)
            current = self._next_window_units(current, unit, anchor)

        self._append_chunk(chunks, current)
        return chunks

    def _build_sections(self, text: str, page_section_path: str | None) -> list[_Section]:
        """按页内标题拆出小节，给每个小节补充分层 section_path。"""

        lines = self._normalize_text(text).splitlines()
        title_info = (
            None
            if page_section_path
            else self._extract_leading_document_title(lines)
        )
        if title_info is not None:
            title, consumed = title_info
            lines = [title, *lines[consumed:]]
        sections: list[_Section] = []
        current_lines: list[str] = []
        current_section_path = page_section_path
        parent_section_path = page_section_path

        for index, line in enumerate(lines):
            if not line:
                continue
            if self._is_heading(line, line_index=index):
                heading = self._normalize_heading_text(line)
                if current_lines:
                    if self._section_has_body(current_lines):
                        sections.append(
                            _Section(
                                text=self._join_units(current_lines),
                                section_path=current_section_path,
                            )
                        )
                    elif self._is_plain_heading(current_lines[0]):
                        parent_section_path = current_section_path
                current_lines = [heading]
                current_section_path = self._join_section_path(parent_section_path, heading)
                if (
                    parent_section_path is None
                    and index == 0
                    and self._is_document_title(heading)
                ):
                    parent_section_path = current_section_path
                continue
            current_lines.append(line)

        if current_lines:
            if self._section_has_body(current_lines) or not self._is_heading(current_lines[0]):
                sections.append(
                    _Section(
                        text=self._join_units(current_lines),
                        section_path=current_section_path or self._extract_section_path(text),
                    )
                )
        return sections

    def _build_units(self, text: str) -> list[str]:
        """构建可打包的语义单元，并合并 PDF 抽取产生的软换行。"""

        units: list[str] = []
        pending_lines: list[str] = []

        def flush_pending() -> None:
            paragraph = self._merge_wrapped_lines(pending_lines)
            pending_lines.clear()
            if not paragraph:
                return
            if self._is_heading(paragraph):
                units.append(self._normalize_heading_text(paragraph))
                return
            units.extend(self._split_line_to_units(paragraph))

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if self._is_heading(line):
                flush_pending()
                units.append(self._normalize_heading_text(line))
                continue
            if self._is_table_line(line):
                flush_pending()
                units.extend(self._split_table_line(line))
                continue
            if self._starts_new_semantic_line(line):
                flush_pending()
            pending_lines.append(line)
        flush_pending()
        return units

    def _split_table_line(self, line: str) -> list[str]:
        """切分超长表格行，避免单行表格突破分块预算。"""

        if len(line) <= self._chunk_size:
            return [line]
        return self._split_long_text(line)

    def _split_line_to_units(self, line: str) -> list[str]:
        """将长行拆成句子单元，避免 PDF 抽取出的整段文本被硬切。"""

        if len(line) <= self._chunk_size:
            return [line]

        units: list[str] = []
        for match in self._SENTENCE_PATTERN.finditer(line):
            sentence = match.group(0).strip()
            if not sentence:
                continue
            if len(sentence) <= self._chunk_size:
                units.append(sentence)
                continue
            units.extend(self._split_long_text(sentence))
        return units

    def _split_long_text(self, text: str) -> list[str]:
        """对无明显句界的超长文本做边界感知字符切分。"""

        cleaned = text.strip()
        if not cleaned:
            return []
        start = 0
        result: list[str] = []
        size = self._chunk_size
        overlap = self._chunk_overlap
        while start < len(cleaned):
            hard_end = min(len(cleaned), start + size)
            end = self._best_boundary(cleaned, start, hard_end)
            chunk = cleaned[start:end].strip()
            if chunk:
                result.append(chunk)
            if end == len(cleaned):
                break
            start = max(end - overlap, start + 1)
        return result

    def _best_boundary(self, text: str, start: int, hard_end: int) -> int:
        """在窗口末尾附近寻找更自然的切点。"""

        if hard_end >= len(text):
            return len(text)
        search_start = max(start + 1, hard_end - 80)
        window = text[search_start:hard_end]
        for boundary in ("。", "！", "？", "；", ";", "，", ",", "、", " "):
            position = window.rfind(boundary)
            if position >= 0:
                return search_start + position + 1
        return hard_end

    def _append_chunk(self, chunks: list[str], units: list[str]) -> None:
        """追加清洗后的 chunk，过滤空白结果。"""

        text = self._join_units(units)
        if text:
            chunks.append(text)

    def _next_window_units(
        self,
        previous_units: list[str],
        next_unit: str,
        anchor: str | None,
    ) -> list[str]:
        """生成下一窗口，使用完整语义单元做 overlap。"""

        overlap_units = self._tail_overlap_units(previous_units)
        result: list[str] = []
        if anchor and anchor not in overlap_units and anchor != next_unit:
            result.append(anchor)
        result.extend(overlap_units)
        result.append(next_unit)
        while len(result) > 1 and len(self._join_units(result)) > self._chunk_size:
            if result[0] == anchor and len(result) > 2:
                result.pop(1)
            else:
                result.pop(0)
        return result

    def _tail_overlap_units(self, units: list[str]) -> list[str]:
        """从上一块尾部取完整语义单元作为重叠上下文。"""

        if self._chunk_overlap <= 0:
            return []
        selected: list[str] = []
        total = 0
        for unit in reversed(units):
            if self._is_heading(unit) and selected:
                continue
            selected.insert(0, unit)
            total += len(unit)
            if total >= self._chunk_overlap:
                break
        return selected

    def _extract_section_path(self, text: str) -> str | None:
        """从页面文本中提取章节标题（启发式）。"""

        for index, raw in enumerate(text.splitlines()):
            line = raw.strip()
            if not line:
                continue
            if self._is_heading(line, line_index=index):
                return line[:100]
        return None

    def _is_heading(self, line: str, line_index: int | None = None) -> bool:
        """判断是否为章节标题或通知类文档标题。"""

        normalized = self._normalize_heading_text(line)
        if len(normalized) > 80:
            return False
        if normalized.startswith(self._SECTION_PREFIXES):
            return True
        for marker in ("章", "节"):
            if normalized.startswith("第") and marker in normalized:
                return True
        if re.match(rf"^[(（]{self._CHINESE_NUMBER_PATTERN}[)）]\S+", normalized):
            return True
        if re.match(rf"^{self._CHINESE_NUMBER_PATTERN}\s+\S+", normalized):
            return True
        if self._is_colon_heading(normalized):
            return True
        if self._is_plain_heading(normalized):
            return True
        if self._is_document_title(normalized):
            return True
        return False

    def _is_document_title(self, line: str) -> bool:
        """识别 PDF 首页常见通知标题，提升检索时的标题命中率。"""

        normalized = self._normalize_heading_text(line)
        if "。" in normalized or "；" in normalized or ";" in normalized:
            return False
        if normalized.endswith(self._DOCUMENT_TITLE_SUFFIXES) and (
            normalized.startswith("关于") or len(normalized) >= 16
        ):
            return True
        return normalized.startswith("关于") and any(
            suffix in normalized for suffix in self._DOCUMENT_TITLE_SUFFIXES
        )

    def _extract_leading_document_title(self, lines: list[str]) -> tuple[str, int] | None:
        """合并 PDF 首页被换行拆开的通知标题。"""

        if not lines:
            return None
        collected: list[str] = []
        for index, line in enumerate(lines[:4]):
            normalized = self._normalize_heading_text(line)
            if not normalized:
                continue
            if index > 0 and self._looks_like_body_start(normalized):
                break
            collected.append(normalized)
            title = self._normalize_heading_text(" ".join(collected))
            if self._is_document_title(title):
                return title[:100], index + 1
        return None

    def _looks_like_body_start(self, line: str) -> bool:
        """识别通知正文开头，避免把称呼并入标题。"""

        return line.endswith(("：", ":")) or line.startswith(("各", "为", "根据"))

    def _is_colon_heading(self, line: str) -> bool:
        """识别通知中常见的短标签标题。"""

        normalized = self._normalize_heading_text(line)
        if len(normalized) > 32:
            return False
        if normalized.startswith("各"):
            return False
        if not normalized.endswith(("：", ":")):
            return False
        return "http" not in normalized.lower()

    def _is_plain_heading(self, line: str) -> bool:
        """识别无冒号但独占一行的短小节标题。"""

        normalized = self._normalize_heading_text(line)
        if len(normalized) > 24:
            return False
        return normalized in {"参与方式"}

    def _starts_new_semantic_line(self, line: str) -> bool:
        """判断当前行是否应作为新的语义单元开始。"""

        normalized = self._normalize_heading_text(line)
        if normalized.startswith(("◆", "●", "-", "·")):
            return True
        if re.match(r"^\d{1,2}([.．、])\s*\D", normalized):
            return True
        if re.match(rf"^[(（]{self._CHINESE_NUMBER_PATTERN}[)）]\S+", normalized):
            return True
        return self._is_colon_heading(normalized)

    def _merge_wrapped_lines(self, lines: list[str]) -> str:
        """合并 PDF 软换行，修复词语和句子被视觉换行拆开的情况。"""

        if not lines:
            return ""
        merged = lines[0].strip()
        for line in lines[1:]:
            normalized = line.strip()
            if not normalized:
                continue
            separator = "" if self._should_join_without_space(merged, normalized) else " "
            merged = f"{merged}{separator}{normalized}"
        return self._normalize_body_text(merged)

    def _should_join_without_space(self, left: str, right: str) -> bool:
        """判断软换行两侧是否应直接拼接。"""

        if not left or not right:
            return False
        if left.endswith(("。", "！", "？", "；", ";", "：", ":", "）", ")")):
            return False
        if right.startswith(("◆", "●", "-", "·")):
            return False
        if left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum():
            return False
        return True

    def _normalize_body_text(self, text: str) -> str:
        """清理 PDF 抽取文本中的异常空格。"""

        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)
        normalized = re.sub(r"\s+([：:，,。；;！？!?）)])", r"\1", normalized)
        normalized = re.sub(r"([（(])\s+", r"\1", normalized)
        return normalized

    def _normalize_heading_text(self, text: str) -> str:
        """归一化标题文本，避免换行与多余空格影响章节路径。"""

        collapsed = re.sub(r"\s+", " ", text).strip()
        if re.match(rf"^{self._CHINESE_NUMBER_PATTERN}\s+\S+", collapsed):
            return collapsed[:100].strip()
        return self._normalize_body_text(text)[:100].strip()

    def _join_section_path(self, parent: str | None, heading: str) -> str:
        """拼接章节路径，避免标题重复。"""

        normalized_heading = heading[:100].strip()
        if not parent:
            return normalized_heading
        normalized_parent = parent.strip()
        if not normalized_parent or normalized_parent.endswith(normalized_heading):
            return normalized_parent or normalized_heading
        return f"{normalized_parent}/{normalized_heading}"

    def _section_has_body(self, lines: list[str]) -> bool:
        """判断小节是否包含标题之外的正文。"""

        return len([line for line in lines if line.strip()]) > 1

    def _join_units(self, units: list[str]) -> str:
        """合并语义单元，表格和标题保留换行。"""

        return "\n".join(unit.strip() for unit in units if unit.strip()).strip()

    def _normalize_text(self, text: str) -> str:
        """统一裁剪空白行，保留换行作为段落边界。"""

        return "\n".join(part.strip() for part in text.splitlines() if part.strip()).strip()

    def _is_table_line(self, line: str) -> bool:
        """识别表格行，避免列关系被句子切分破坏。"""

        return " | " in line or line.count("|") >= 2
