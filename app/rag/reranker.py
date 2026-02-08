from __future__ import annotations

from app.rag.vector_store import VectorHit


class SimpleReranker:
    """简单重排器（基于关键词覆盖度的启发式实现）。"""

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """根据问题关键词覆盖度重排命中结果。"""

        if not hits:
            return hits
        tokens = self._tokenize(question)
        if not tokens:
            return hits
        return sorted(
            hits,
            key=lambda item: (self._overlap_score(tokens, item), item.score),
            reverse=True,
        )

    def _tokenize(self, text: str) -> list[str]:
        """将问题拆分为关键词列表（中文以字符兜底）。"""

        stripped = text.strip()
        if not stripped:
            return []
        tokens = stripped.split()
        if len(tokens) > 1:
            return tokens
        if tokens and len(tokens[0]) <= 2:
            return tokens
        return [char for char in stripped if char.strip()]

    def _overlap_score(self, tokens: list[str], hit: VectorHit) -> int:
        """计算关键词覆盖度分数。"""

        content = (hit.payload.get("text") or "").lower()
        if not content:
            return 0
        score = 0
        for token in tokens:
            if token.lower() in content:
                score += 1
        return score
