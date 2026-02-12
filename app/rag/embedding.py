from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

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
        self._endpoint = _build_embedding_endpoint(
            settings.embedding_base_url,
            settings.embedding_api_path,
        )
        self._model = settings.embedding_model_name
        self._timeout = settings.embedding_timeout_s
        self._api_key = settings.embedding_api_key
        self._batch_size = max(1, settings.embedding_batch_size)
        self._expected_dim = settings.vector_dim
        self._dimensions = settings.embedding_dimensions

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

        payload: dict[str, Any] = {"model": self._model, "input": texts}
        if self._dimensions is not None:
            payload["dimensions"] = self._dimensions
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = httpx.post(
                self._endpoint,
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
                detail={
                    "status_code": response.status_code,
                    "body": _extract_response_body(response),
                },
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


class LocalEmbeddingClient:
    """本地 Embedding 客户端（方案 3 扩展埋点）。"""

    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.local_embedding_model_name
        self._device = settings.local_embedding_device
        self._normalize = settings.local_embedding_normalize
        self._batch_size = max(1, settings.embedding_batch_size)
        self._expected_dim = settings.vector_dim
        self._model: Any | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。"""

        if not texts:
            return []
        model = self._load_model()
        try:
            vectors = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="本地 Embedding 推理失败",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc
        embeddings = _normalize_vectors(vectors)
        self._validate_dim(embeddings)
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """生成查询向量。"""

        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []

    def _load_model(self) -> Any:
        """惰性加载本地模型，避免进程启动时的额外开销。"""

        if self._model is not None:
            return self._model
        sentence_transformer_cls = self._load_sentence_transformer_cls()
        try:
            self._model = sentence_transformer_cls(self._model_name, device=self._device)
        except Exception as exc:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="加载本地 Embedding 模型失败",
                detail={"model": self._model_name, "device": self._device, "error": str(exc)},
                status_code=500,
            ) from exc
        return self._model

    @staticmethod
    def _load_sentence_transformer_cls() -> Any:
        """动态导入 sentence-transformers，作为本地模式扩展点。"""

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="本地 Embedding 依赖缺失，请安装 sentence-transformers",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc
        return SentenceTransformer

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


_embedder: Embedder | None = None


def get_embedder(settings: Settings) -> Embedder:
    """获取向量化实例（按配置选择后端）。"""

    global _embedder
    if _embedder is None:
        if settings.embedding_backend == "http":
            _embedder = HttpEmbeddingClient(settings)
        elif settings.embedding_backend == "simple":
            _embedder = SimpleEmbedder(settings.vector_dim)
        else:
            _embedder = LocalEmbeddingClient(settings)
    return _embedder


def reset_embedder() -> None:
    """重置向量化实例（测试使用）。"""

    global _embedder
    _embedder = None


def _build_embedding_endpoint(base_url: str, api_path: str) -> str:
    """拼接 Embedding 请求地址。"""

    normalized_base = base_url.rstrip("/")
    normalized_path = api_path.strip() or "/embeddings"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{normalized_base}{normalized_path}"


def _extract_response_body(response: httpx.Response) -> object:
    """提取错误响应体，优先返回 JSON 结构。"""

    try:
        return response.json()
    except Exception:
        return response.text


def _normalize_vectors(value: Any) -> list[list[float]]:
    """标准化本地模型输出为二维 float 列表。"""

    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list):
        raise AppError(
            code=ErrorCode.EMBEDDING_FAILED,
            message="本地 Embedding 返回数据格式异常",
            detail={"value_type": type(value).__name__},
            status_code=500,
        )
    vectors: list[list[float]] = []
    for item in value:
        if not isinstance(item, list):
            raise AppError(
                code=ErrorCode.EMBEDDING_FAILED,
                message="本地 Embedding 向量格式异常",
                detail={"item_type": type(item).__name__},
                status_code=500,
            )
        vectors.append([float(vector_item) for vector_item in item])
    return vectors
