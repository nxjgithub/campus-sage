from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Integral
from threading import Lock
from types import SimpleNamespace
from typing import Any, Callable, TypeVar, Protocol
from uuid import UUID, uuid5

import httpx

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings

_QDRANT_POINT_ID_NAMESPACE = UUID("57f77fb8-1ab8-41bb-b4f7-438f68f71f89")


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
            if not _is_published_after_matched(payload, published_after):
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
        self._qdrant_timeout_s = max(1, settings.qdrant_timeout_s)
        self._upsert_batch_size = max(1, settings.qdrant_upsert_batch_size)
        self._client_lock = Lock()
        self._operation_lock = Lock()
        self._client = self._create_client()
        self._collection_prefix = settings.qdrant_collection_prefix
        self._vector_dim = settings.vector_dim
        self._rest = rest

    def upsert(self, kb_id: str, entries: list[VectorEntry]) -> None:
        try:
            self._run_with_retry(lambda: self._upsert_impl(kb_id, entries))
        except AppError:
            raise
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

        query_filter, _ = self._build_query_filter(
            filters, include_published_after=True
        )
        search_limit = topk
        if filters and filters.get("published_after"):
            # 过滤发生在检索后时需要拉取更多候选，避免 TopK 被不满足条件的数据占满。
            search_limit = max(topk, min(max(1, topk) * 5, 200))

        try:
            results = self._run_with_retry(
                lambda: self._search_points(
                    kb_id=kb_id,
                    query_vector=query_vector,
                    limit=search_limit,
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
        hits = self._apply_post_filters(hits, filters)
        if not filters or not filters.get("published_after"):
            return hits[: max(0, topk)]

        if len(hits) >= topk:
            return hits[: max(0, topk)]

        # 兼容历史数据：旧向量可能没有 published_at_ts，补一次无发布日期下推的查询。
        fallback_filter, _ = self._build_query_filter(
            filters, include_published_after=False
        )
        fallback_limit = max(search_limit, min(max(1, topk) * 10, 500))
        try:
            fallback_results = self._run_with_retry(
                lambda: self._search_points(
                    kb_id=kb_id,
                    query_vector=query_vector,
                    limit=fallback_limit,
                    query_filter=fallback_filter,
                )
            )
        except Exception:
            return hits[: max(0, topk)]
        merged = self._merge_hits(
            hits,
            [
                VectorHit(score=result.score, payload=result.payload or {})
                for result in fallback_results
            ],
        )
        return self._apply_post_filters(merged, filters)[: max(0, topk)]

    def _collection_name(self, kb_id: str) -> str:
        return f"{self._collection_prefix}{kb_id}"

    def _create_client(self) -> Any:
        """创建 Qdrant 客户端。"""

        return self._client_cls(
            url=self._qdrant_url,
            api_key=self._qdrant_api_key,
            check_compatibility=False,
            prefer_grpc=False,
            timeout=self._qdrant_timeout_s,
            trust_env=False,
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
        if not entries:
            return
        self._ensure_collection(kb_id)
        collection_name = self._collection_name(kb_id)
        for batch in _chunk_list(entries, self._upsert_batch_size):
            points = [
                self._rest.PointStruct(
                    id=_to_qdrant_point_id(str(entry.payload["chunk_id"])),
                    vector=entry.vector,
                    payload=entry.payload,
                )
                for entry in batch
            ]
            self._client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )

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

    def _build_query_filter(
        self,
        filters: dict[str, Any] | None,
        include_published_after: bool,
    ) -> tuple[Any | None, bool]:
        """构建 Qdrant 查询过滤器。"""

        if not filters:
            return None, False
        must_conditions: list[Any] = []
        doc_ids = filters.get("doc_ids")
        if doc_ids:
            must_conditions.append(
                self._rest.FieldCondition(
                    key="doc_id",
                    match=self._rest.MatchAny(any=doc_ids),
                )
            )
        published_after_pushed = False
        published_after = filters.get("published_after")
        if include_published_after and published_after:
            published_after_ts = _parse_timestamp(published_after)
            if published_after_ts is not None:
                must_conditions.append(
                    self._rest.FieldCondition(
                        key="published_at_ts",
                        range=self._rest.Range(gte=published_after_ts),
                    )
                )
                published_after_pushed = True
        if not must_conditions:
            return None, False
        return self._rest.Filter(must=must_conditions), published_after_pushed

    def _apply_post_filters(
        self, hits: list[VectorHit], filters: dict[str, Any] | None
    ) -> list[VectorHit]:
        """统一应用后置过滤，确保行为在不同后端保持一致。"""

        if not filters:
            return hits
        filtered = hits
        doc_ids = filters.get("doc_ids")
        if doc_ids:
            filtered = [
                hit for hit in filtered if hit.payload.get("doc_id") in doc_ids
            ]
        published_after = filters.get("published_after")
        if published_after:
            filtered = [
                hit
                for hit in filtered
                if _is_published_after_matched(hit.payload, published_after)
            ]
        return filtered

    def _merge_hits(
        self, base_hits: list[VectorHit], fallback_hits: list[VectorHit]
    ) -> list[VectorHit]:
        """按分数去重合并两批命中结果。"""

        seen: set[str] = set()
        merged: list[VectorHit] = []
        for hit in [*base_hits, *fallback_hits]:
            key = str(hit.payload.get("chunk_id") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(hit)
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged

    def _search_points(
        self,
        kb_id: str,
        query_vector: list[float],
        limit: int,
        query_filter: Any | None,
    ) -> list[Any]:
        """兼容不同 qdrant-client 版本的检索接口。"""

        collection_name = self._collection_name(kb_id)
        search = getattr(self._client, "search", None)
        if callable(search):
            return search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                query_filter=query_filter,
            )
        try:
            return self._search_points_rest_compat(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
            )
        except AppError as exc:
            status_code = exc.detail.get("status_code") if isinstance(exc.detail, dict) else None
            if status_code not in {404, 405}:
                raise
        query_points = getattr(self._client, "query_points", None)
        if callable(query_points):
            response = query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
                query_filter=query_filter,
            )
            points = getattr(response, "points", None)
            if isinstance(points, list):
                return points
            raise AppError(
                code=ErrorCode.VECTOR_SEARCH_FAILED,
                message="Qdrant 检索响应格式异常",
                detail={"response_type": type(response).__name__},
                status_code=503,
            )
        raise AppError(
            code=ErrorCode.VECTOR_SEARCH_FAILED,
            message="当前 qdrant-client 不支持检索接口",
            detail={"client_type": type(self._client).__name__},
            status_code=503,
        )

    def _search_points_rest_compat(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        query_filter: Any | None,
    ) -> list[Any]:
        """使用兼容旧版 Qdrant 服务端的 REST 搜索接口。"""

        payload: dict[str, Any] = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
        }
        if query_filter is not None:
            payload["filter"] = self._dump_rest_model(query_filter)
        headers: dict[str, str] = {}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        response = httpx.post(
            f"{self._qdrant_url.rstrip('/')}/collections/{collection_name}/points/search",
            json=payload,
            headers=headers,
            timeout=self._qdrant_timeout_s,
            trust_env=False,
        )
        if response.status_code != 200:
            raise AppError(
                code=ErrorCode.VECTOR_SEARCH_FAILED,
                message="Qdrant REST 检索失败",
                detail={
                    "status_code": response.status_code,
                    "body": _extract_http_response_body(response),
                },
                status_code=503,
            )
        data = response.json()
        results = data.get("result")
        if not isinstance(results, list):
            raise AppError(
                code=ErrorCode.VECTOR_SEARCH_FAILED,
                message="Qdrant REST 检索响应格式异常",
                detail={"response": data},
                status_code=503,
            )
        return [
            SimpleNamespace(
                score=float(item.get("score", 0.0)),
                payload=item.get("payload") or {},
            )
            for item in results
        ]

    @staticmethod
    def _dump_rest_model(value: Any) -> Any:
        """将 Qdrant Pydantic 模型转换为可序列化字典。"""

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(by_alias=True, exclude_none=True)
        dict_method = getattr(value, "dict", None)
        if callable(dict_method):
            return dict_method(by_alias=True, exclude_none=True)
        return value

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
        _raise_payload_type_error("kb_id", payload.get("kb_id"))
    if not _is_non_empty_str(payload.get("doc_id")):
        _raise_payload_type_error("doc_id", payload.get("doc_id"))
    if not _is_non_empty_str(payload.get("doc_name")):
        _raise_payload_type_error("doc_name", payload.get("doc_name"))
    if not _is_optional_str(payload.get("doc_version")):
        _raise_payload_type_error("doc_version", payload.get("doc_version"))
    if not _is_optional_str(payload.get("published_at")):
        _raise_payload_type_error("published_at", payload.get("published_at"))
    if "source_type" in payload and not _is_optional_str(payload.get("source_type")):
        _raise_payload_type_error("source_type", payload.get("source_type"))
    if "source_uri" in payload and not _is_optional_str(payload.get("source_uri")):
        _raise_payload_type_error("source_uri", payload.get("source_uri"))
    if "published_at_ts" in payload and not _is_optional_int(payload.get("published_at_ts")):
        _raise_payload_type_error("published_at_ts", payload.get("published_at_ts"))
    if not _is_optional_int(payload.get("page_start")):
        _raise_payload_type_error("page_start", payload.get("page_start"))
    if not _is_optional_int(payload.get("page_end")):
        _raise_payload_type_error("page_end", payload.get("page_end"))
    if not _is_optional_str(payload.get("section_path")):
        _raise_payload_type_error("section_path", payload.get("section_path"))
    if not _is_non_empty_str(payload.get("chunk_id")):
        _raise_payload_type_error("chunk_id", payload.get("chunk_id"))
    if not _is_int(payload.get("chunk_index")):
        _raise_payload_type_error("chunk_index", payload.get("chunk_index"))
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        _raise_payload_type_error("text", text)


def _raise_payload_type_error(field: str, value: object) -> None:
    """抛出 payload 字段类型错误。"""

    value_preview = repr(value)
    if len(value_preview) > 120:
        value_preview = f"{value_preview[:117]}..."
    raise AppError(
        code=ErrorCode.RAG_PAYLOAD_INVALID,
        message="向量 payload 字段类型不合法",
        detail={
            "field": field,
            "actual_type": type(value).__name__,
            "value_preview": value_preview,
        },
        status_code=500,
    )


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_int(value: object) -> bool:
    return isinstance(value, Integral) and not isinstance(value, bool)


def _is_optional_int(value: object) -> bool:
    return value is None or _is_int(value)


def _parse_timestamp(value: object) -> int | None:
    """解析日期时间为 UTC 秒级时间戳。"""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())


def _is_published_after_matched(payload: dict[str, Any], published_after: object) -> bool:
    """判断单条 payload 是否满足发布日期下限。"""

    if not isinstance(published_after, str) or not published_after.strip():
        return True
    threshold_ts = _parse_timestamp(published_after)
    payload_ts = payload.get("published_at_ts")
    if threshold_ts is not None and isinstance(payload_ts, int):
        return payload_ts >= threshold_ts
    published_at = payload.get("published_at")
    if published_at is None:
        return False
    return str(published_at) >= published_after


def _to_qdrant_point_id(chunk_id: str) -> str:
    """将业务 chunk_id 映射为 Qdrant 支持的稳定 UUID。"""

    return str(uuid5(_QDRANT_POINT_ID_NAMESPACE, chunk_id))


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


def _chunk_list(items: list[VectorEntry], batch_size: int) -> list[list[VectorEntry]]:
    """按批次切分列表。"""

    if batch_size <= 0:
        return [items]
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _extract_http_response_body(response: httpx.Response) -> object:
    """提取 HTTP 错误响应体，优先返回 JSON。"""

    try:
        return response.json()
    except Exception:
        return response.text
