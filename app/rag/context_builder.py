from __future__ import annotations

from dataclasses import dataclass

from app.rag.vector_store import VectorHit


@dataclass(slots=True)
class ContextBuildResult:
    context: str
    hits: list[VectorHit]


class ContextBuilder:
    """上下文构造器（含预算与去重）。"""

    def __init__(self, max_context_tokens: int) -> None:
        self._max_tokens = max(1, max_context_tokens)

    def build(self, hits: list[VectorHit]) -> ContextBuildResult:
        """构造上下文并返回选择的命中。"""

        selected: list[VectorHit] = []
        texts: list[str] = []
        used_tokens = 0
        seen = set()

        for index, hit in enumerate(hits, start=1):
            payload = hit.payload
            key = (payload.get("doc_id"), payload.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            text = (payload.get("text") or "").strip()
            if not text:
                continue
            tokens = self._estimate_tokens(text)
            if used_tokens + tokens > self._max_tokens:
                continue
            used_tokens += tokens
            selected.append(hit)
            texts.append(self._format_context(index, payload, text))

        context = "\n".join(texts)
        return ContextBuildResult(context=context, hits=selected)

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数（以字符数近似，便于快速裁剪）。"""

        return max(1, len(text))

    def _format_context(self, index: int, payload: dict, text: str) -> str:
        """格式化单条上下文。"""

        doc_name = payload.get("doc_name") or "未知文档"
        page_start = payload.get("page_start")
        page_end = payload.get("page_end")
        section_path = payload.get("section_path")
        location = ""
        if section_path:
            location = f"章节:{section_path}"
        elif page_start is not None:
            location = f"页码:{page_start}-{page_end or page_start}"
        return f"[证据{index} 来源:{doc_name} {location}]\n{text}"
