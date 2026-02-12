from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


class Embedder(Protocol):
    """向量化接口（便于切换后端）。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SimpleEmbedder:
    """简单可复现的向量化实现（兜底方案）。"""

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


class HttpEmbeddingClient:
    """OpenAI 兼容的 Embedding 客户端。"""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.embedding_base_url.rstrip("/")
        self._model = settings.embedding_model_name
        self._timeout = settings.embedding_timeout_s
        self._api_key = settings.embedding_api_key
        self._batch_size = max(1, settings.embedding_batch_size)
        self._expected_dim = settings.vector_dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。"""

        if not texts:
            return []
        embeddings: list[list[float]] = []
        for batch in self._batch(texts, self._batch_size):
            embeddings.extend(self._request_embeddings(batch))
        self._validate_dim(embeddings)
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """生成查询向量。"""

        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """调用 Embedding 服务。"""

        payload = {"model": self._model, "input": texts}
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="Embedding 服务不可用",
                detail={"error": str(exc)},
                status_code=502,
            ) from exc
        if response.status_code != 200:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="Embedding 服务返回异常状态",
                detail={"status_code": response.status_code, "body": response.text},
                status_code=502,
            )
        data = response.json()
        items = data.get("data") or []
        if not items:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="Embedding 服务未返回结果",
                detail={"response": data},
                status_code=502,
            )
        items = sorted(items, key=lambda item: item.get("index", 0))
        embeddings = [self._normalize_embedding(item.get("embedding")) for item in items]
        if len(embeddings) != len(texts):
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="Embedding 返回数量不匹配",
                detail={"expected": len(texts), "actual": len(embeddings)},
                status_code=502,
            )
        return embeddings

    def _normalize_embedding(self, value: object) -> list[float]:
        """标准化向量值为 float 列表。"""

        if not isinstance(value, list):
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="Embedding 返回数据格式异常",
                detail={"value_type": type(value).__name__},
                status_code=502,
            )
        return [float(item) for item in value]

    def _validate_dim(self, embeddings: list[list[float]]) -> None:
        """校验向量维度一致性。"""

        if self._expected_dim <= 0:
            return
        for embedding in embeddings:
            if len(embedding) != self._expected_dim:
                raise AppError(
                    code=ErrorCode.EMBEDDING_FAILED,
                    message="Embedding 维度不匹配",
                    detail={"expected": self._expected_dim, "actual": len(embedding)},
                    status_code=500,
                )

    @staticmethod
    def _batch(items: list[str], batch_size: int) -> list[list[str]]:
        """按批次拆分文本列表。"""

        return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


_embedder: Embedder | None = None


def get_embedder(settings: Settings) -> Embedder:
    """获取向量化实例（按配置选择后端）。"""

    global _embedder
    if _embedder is None:
        if settings.embedding_backend == "http":
            _embedder = HttpEmbeddingClient(settings)
        else:
            _embedder = SimpleEmbedder(settings.vector_dim)
    return _embedder
