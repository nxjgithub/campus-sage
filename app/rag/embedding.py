from __future__ import annotations

import hashlib
import math


class SimpleEmbedder:
    """简单可复现的向量化实现（MVP 兜底）。"""

    def __init__(self, vector_dim: int) -> None:
        self._vector_dim = max(1, vector_dim)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。"""

        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """生成查询向量。"""

        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        """基于哈希的简单向量化。"""

        vector = [0.0] * self._vector_dim
        tokens = text.split()
        if not tokens:
            tokens = list(text)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self._vector_dim
            vector[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
