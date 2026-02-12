from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, TypeVar, Protocol

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


@dataclass(slots=True)
class VectorEntry:
    vector: list[float]
    payload: dict[str, Any]


@dataclass(slots=True)
class VectorHit:
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    """向量库接口。"""

    def upsert(self, kb_id: str, entries: list[VectorEntry]) -> None: ...

    def delete_by_doc_id(self, kb_id: str, doc_id: str) -> None: ...

    def delete_by_kb_id(self, kb_id: str) -> None: ...

    def search(
        self,
        kb_id: str,
        query_vector: list[float],
        topk: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]: ...


class InMemoryVectorStore:
    """内存向量库（MVP 兜底实现）。"""

    def __init__(self) -> None:
        self._items: dict[str, list[VectorEntry]] = {}
        self._lock = Lock()

    def upsert(self, kb_id: str, entries: list[VectorEntry]) -> None:
        """写入向量数据。"""

        _validate_entries(entries)
        with self._lock:
            self._items.setdefault(kb_id, [])
            self._items[kb_id].extend(entries)

    def delete_by_doc_id(self, kb_id: str, doc_id: str) -> None:
        """按 doc_id 删除向量。"""

        with self._lock:
            items = self._items.get(kb_id, [])
            self._items[kb_id] = [
                entry for entry in items if entry.payload.get("doc_id") != doc_id
            ]

    def delete_by_kb_id(self, kb_id: str) -> None:
        """按 kb_id 删除全部向量。"""

        with self._lock:
            self._items.pop(kb_id, None)

    def search(
        self,
        kb_id: str,
        query_vector: list[float],
        topk: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """向量检索。"""

        with self._lock:
            items = list(self._items.get(kb_id, []))
        hits: list[VectorHit] = []
        for entry in items:
            if not self._match_filters(entry.payload, filters):
                continue
            score = self._cosine(query_vector, entry.vector)
            hits.append(VectorHit(score=score, payload=entry.payload))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: max(0, topk)]

    def _match_filters(self, payload: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        doc_ids = filters.get("doc_ids")
        if doc_ids and payload.get("doc_id") not in doc_ids:
            return False
        published_after = filters.get("published_after")
        if published_after:
            published_at = payload.get("published_at")
            if published_at is None or published_at < published_after:
                return False
        return True

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

class QdrantVectorStore:
    """Qdrant 向量库实现（可选依赖）。"""

    def __init__(self, settings: Settings) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore
            from qdrant_client.http import models as rest  # type: ignore
        except Exception as exc:  # pragma: no cover - 依赖缺失时触发
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="缺少 Qdrant 依赖，请安装 qdrant-client",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc

        self._client_cls = QdrantClient
        self._qdrant_url = settings.qdrant_url
        self._qdrant_api_key = settings.qdrant_api_key
        self._client_lock = Lock()
        self._operation_lock = Lock()
        self._client = self._create_client()
        self._collection_prefix = settings.qdrant_collection_prefix
        self._vector_dim = settings.vector_dim
        self._rest = rest

    def upsert(self, kb_id: str, entries: list[VectorEntry]) -> None:
        try:
            self._run_with_retry(lambda: self._upsert_impl(kb_id, entries))
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="向量库不可用，无法写入",
                detail={"error": str(exc)},
                status_code=503,
            ) from exc

    def delete_by_doc_id(self, kb_id: str, doc_id: str) -> None:
        try:
            self._run_with_retry(lambda: self._delete_by_doc_id_impl(kb_id, doc_id))
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="向量库不可用，无法删除",
                detail={"error": str(exc)},
                status_code=503,
            ) from exc

    def delete_by_kb_id(self, kb_id: str) -> None:
        try:
            self._run_with_retry(lambda: self._delete_by_kb_id_impl(kb_id))
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="向量库不可用，无法删除集合",
                detail={"error": str(exc)},
                status_code=503,
            ) from exc

    def search(
        self,
        kb_id: str,
        query_vector: list[float],
        topk: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        try:
            if not self._run_with_retry(lambda: self._collection_exists(kb_id)):
                return []
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_SEARCH_FAILED,
                message="向量库不可用，无法检索",
                detail={"error": str(exc)},
                status_code=503,
            ) from exc

        query_filter = None
        if filters and filters.get("doc_ids"):
            condition = self._rest.FieldCondition(
                key="doc_id",
                match=self._rest.MatchAny(any=filters["doc_ids"]),
            )
            query_filter = self._rest.Filter(must=[condition])

        try:
            results = self._run_with_retry(
                lambda: self._client.search(
                    collection_name=self._collection_name(kb_id),
                    query_vector=query_vector,
                    limit=topk,
                    with_payload=True,
                    query_filter=query_filter,
                )
            )
            hits = [
                VectorHit(score=result.score, payload=result.payload or {})
                for result in results
            ]
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_SEARCH_FAILED,
                message="向量库不可用，无法检索",
                detail={"error": str(exc)},
                status_code=503,
            ) from exc
        if filters and filters.get("published_after"):
            hits = [
                hit
                for hit in hits
                if (hit.payload.get("published_at") or "") >= filters["published_after"]
            ]
        return hits

    def _collection_name(self, kb_id: str) -> str:
        return f"{self._collection_prefix}{kb_id}"

    def _create_client(self) -> Any:
        """创建 Qdrant 客户端。"""

        return self._client_cls(
            url=self._qdrant_url,
            api_key=self._qdrant_api_key,
            check_compatibility=False,
            timeout=10,
        )

    def _reset_client(self) -> None:
        """重建 Qdrant 客户端（处理连接断开场景）。"""

        with self._client_lock:
            old_client = self._client
            self._client = self._create_client()
            close = getattr(old_client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def _upsert_impl(self, kb_id: str, entries: list[VectorEntry]) -> None:
        """写入向量数据。"""

        _validate_entries(entries)
        self._ensure_collection(kb_id)
        points = [
            self._rest.PointStruct(
                id=entry.payload["chunk_id"],
                vector=entry.vector,
                payload=entry.payload,
            )
            for entry in entries
        ]
        self._client.upsert(collection_name=self._collection_name(kb_id), points=points)

    def _delete_by_doc_id_impl(self, kb_id: str, doc_id: str) -> None:
        """按 doc_id 删除向量数据。"""

        if not self._collection_exists(kb_id):
            return
        condition = self._rest.FieldCondition(
            key="doc_id", match=self._rest.MatchValue(value=doc_id)
        )
        self._client.delete(
            collection_name=self._collection_name(kb_id),
            points_selector=self._rest.Filter(must=[condition]),
        )

    def _delete_by_kb_id_impl(self, kb_id: str) -> None:
        """按 kb_id 删除集合。"""

        if not self._collection_exists(kb_id):
            return
        self._client.delete_collection(collection_name=self._collection_name(kb_id))

    def _ensure_collection(self, kb_id: str) -> None:
        name = self._collection_name(kb_id)
        if self._collection_exists(kb_id):
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=self._rest.VectorParams(
                size=self._vector_dim, distance=self._rest.Distance.COSINE
            ),
        )

    def _collection_exists(self, kb_id: str) -> bool:
        name = self._collection_name(kb_id)
        collections = self._client.get_collections().collections
        return name in {collection.name for collection in collections}

    _T = TypeVar("_T")

    def _run_with_retry(self, operation: Callable[[], _T]) -> _T:
        """执行向量库操作，遇到断连时重试一次。"""

        with self._operation_lock:
            try:
                return operation()
            except Exception as exc:
                if not _is_disconnect_error(exc):
                    raise
                self._reset_client()
                return operation()


_vector_store: VectorStore | None = None


def get_vector_store(settings: Settings) -> VectorStore:
    """获取向量库实例（按配置选择后端）。"""

    global _vector_store
    if _vector_store is None:
        if settings.vector_backend == "qdrant":
            _vector_store = QdrantVectorStore(settings)
        else:
            _vector_store = InMemoryVectorStore()
    return _vector_store


def _validate_entries(entries: list[VectorEntry]) -> None:
    """校验向量 payload 是否符合契约。"""

    for entry in entries:
        _validate_payload(entry.payload)


def _validate_payload(payload: dict[str, Any]) -> None:
    """校验单条 payload 字段完整性与类型。"""

    required_fields = [
        "contract_version",
        "kb_id",
        "doc_id",
        "doc_name",
        "doc_version",
        "published_at",
        "page_start",
        "page_end",
        "section_path",
        "chunk_id",
        "chunk_index",
        "text",
    ]
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise AppError(
            code=ErrorCode.RAG_PAYLOAD_INVALID,
            message="向量 payload 缺少必填字段",
            detail={"missing": missing},
            status_code=500,
        )
    if payload.get("contract_version") != "0.1":
        raise AppError(
            code=ErrorCode.RAG_PAYLOAD_INVALID,
            message="向量 payload 契约版本不匹配",
            detail={"contract_version": payload.get("contract_version")},
            status_code=500,
        )
    if not _is_non_empty_str(payload.get("kb_id")):
        _raise_payload_type_error("kb_id")
    if not _is_non_empty_str(payload.get("doc_id")):
        _raise_payload_type_error("doc_id")
    if not _is_non_empty_str(payload.get("doc_name")):
        _raise_payload_type_error("doc_name")
    if not _is_optional_str(payload.get("doc_version")):
        _raise_payload_type_error("doc_version")
    if not _is_optional_str(payload.get("published_at")):
        _raise_payload_type_error("published_at")
    if not _is_optional_int(payload.get("page_start")):
        _raise_payload_type_error("page_start")
    if not _is_optional_int(payload.get("page_end")):
        _raise_payload_type_error("page_end")
    if not _is_optional_str(payload.get("section_path")):
        _raise_payload_type_error("section_path")
    if not _is_non_empty_str(payload.get("chunk_id")):
        _raise_payload_type_error("chunk_id")
    if not isinstance(payload.get("chunk_index"), int):
        _raise_payload_type_error("chunk_index")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        _raise_payload_type_error("text")


def _raise_payload_type_error(field: str) -> None:
    """抛出 payload 字段类型错误。"""

    raise AppError(
        code=ErrorCode.RAG_PAYLOAD_INVALID,
        message="向量 payload 字段类型不合法",
        detail={"field": field},
        status_code=500,
    )


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_optional_int(value: object) -> bool:
    return value is None or isinstance(value, int)


def _is_disconnect_error(exc: Exception) -> bool:
    """判断是否为连接中断类错误。"""

    message = str(exc).lower()
    disconnect_patterns = [
        "server disconnected without sending a response",
        "connection reset by peer",
        "connection aborted",
        "connection refused",
        "remoteprotocolerror",
        "timed out",
    ]
    return any(pattern in message for pattern in disconnect_patterns)
