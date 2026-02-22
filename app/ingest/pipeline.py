from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Callable

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.core.utils import new_id, utc_now_iso
from app.ingest.chunker import Chunker
from app.ingest.dto import IngestResult
from app.ingest.parser import DocumentParser
from app.rag.embedding import Embedder, get_embedder
from app.rag.vector_store import VectorEntry, VectorStore, get_vector_store

class IngestPipeline:
    """入库流水线（解析 → 切分 → 向量化 → 写入向量库）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._parser = DocumentParser()
        self._chunker = Chunker(settings.chunk_size, settings.chunk_overlap)
        self._embedder: Embedder = get_embedder(settings)
        self._vector_store: VectorStore = get_vector_store(settings)

    def run(
        self,
        kb_id: str,
        doc_id: str,
        doc_name: str,
        doc_version: str | None,
        published_at: str | None,
        file_path: str,
        cancel_checker: Callable[[], bool] | None = None,
        progress_callback: Callable[[str, dict[str, int]], None] | None = None,
    ) -> IngestResult:
        """执行入库流程。"""

        self._check_cancel(cancel_checker)
        total_start = time.perf_counter()
        parse_start = time.perf_counter()
        try:
            pages = self._parser.parse(path=file_path)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="解析文档失败",
                detail={"error": str(exc)},
                status_code=400,
            ) from exc
        parse_ms = int((time.perf_counter() - parse_start) * 1000)
        self._report_progress(
            progress_callback,
            stage="parse",
            pages_parsed=len(pages),
            chunks_built=0,
            embeddings_done=0,
            vectors_upserted=0,
            stage_ms=parse_ms,
            parse_ms=parse_ms,
        )
        self._check_cancel(cancel_checker)

        chunk_start = time.perf_counter()
        try:
            chunks = self._chunker.build(pages)
        except Exception as exc:
            raise AppError(
                code=ErrorCode.INGEST_CHUNK_FAILED,
                message="切分文档失败",
                detail={"error": str(exc)},
                status_code=400,
            ) from exc
        chunk_ms = int((time.perf_counter() - chunk_start) * 1000)
        self._report_progress(
            progress_callback,
            stage="chunk",
            pages_parsed=len(pages),
            chunks_built=len(chunks),
            embeddings_done=0,
            vectors_upserted=0,
            stage_ms=chunk_ms,
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
        )
        self._check_cancel(cancel_checker)

        texts = [chunk.text for chunk in chunks]
        embed_start = time.perf_counter()
        try:
            vectors = self._embedder.embed_texts(texts)
        except AppError as exc:
            raise AppError(
                code=ErrorCode.INGEST_EMBED_FAILED,
                message="向量化失败",
                detail={
                    "source_code": exc.code.value,
                    "source_message": exc.message,
                    "source_detail": exc.detail,
                },
                status_code=exc.status_code,
            ) from exc
        except Exception as exc:
            raise AppError(
                code=ErrorCode.INGEST_EMBED_FAILED,
                message="向量化失败",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc
        embed_ms = int((time.perf_counter() - embed_start) * 1000)
        self._report_progress(
            progress_callback,
            stage="embed",
            pages_parsed=len(pages),
            chunks_built=len(chunks),
            embeddings_done=len(vectors),
            vectors_upserted=0,
            stage_ms=embed_ms,
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
        )
        self._check_cancel(cancel_checker)
        if len(chunks) != len(vectors):
            raise AppError(
                code=ErrorCode.INGEST_EMBED_FAILED,
                message="向量化结果数量与分块数量不一致",
                detail={"chunk_count": len(chunks), "vector_count": len(vectors)},
                status_code=500,
            )

        entries = []
        created_at = utc_now_iso()
        published_at_ts = _parse_timestamp(published_at)
        for chunk, vector in zip(chunks, vectors, strict=True):
            payload = {
                "contract_version": "0.1",
                "kb_id": kb_id,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_version": doc_version,
                "published_at": published_at,
                "published_at_ts": published_at_ts,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_path": chunk.section_path,
                "chunk_id": new_id("chunk"),
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "hash": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                "source_type": "pdf",
                "source_uri": None,
                "tokens": None,
                "created_at": created_at,
            }
            entries.append(VectorEntry(vector=vector, payload=payload))

        upsert_start = time.perf_counter()
        try:
            self._vector_store.upsert(kb_id=kb_id, entries=entries)
        except AppError as exc:
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="向量写入失败",
                detail={
                    "source_code": exc.code.value,
                    "source_message": exc.message,
                    "source_detail": exc.detail,
                },
                status_code=exc.status_code,
            ) from exc
        except Exception as exc:
            raise AppError(
                code=ErrorCode.VECTOR_UPSERT_FAILED,
                message="向量写入失败",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc
        upsert_ms = int((time.perf_counter() - upsert_start) * 1000)
        self._report_progress(
            progress_callback,
            stage="upsert",
            pages_parsed=len(pages),
            chunks_built=len(chunks),
            embeddings_done=len(vectors),
            vectors_upserted=len(entries),
            stage_ms=upsert_ms,
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
            upsert_ms=upsert_ms,
        )
        self._check_cancel(cancel_checker)
        total_ms = int((time.perf_counter() - total_start) * 1000)

        return IngestResult(
            pages_parsed=len(pages),
            chunk_count=len(chunks),
            embed_count=len(vectors),
            upsert_count=len(entries),
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
            upsert_ms=upsert_ms,
            total_ms=total_ms,
        )

    def _check_cancel(self, cancel_checker: Callable[[], bool] | None) -> None:
        """检查是否需要取消入库。"""

        if cancel_checker and cancel_checker():
            raise IngestCanceled("入库已取消")

    def _report_progress(
        self,
        progress_callback: Callable[[str, dict[str, int]], None] | None,
        stage: str,
        pages_parsed: int,
        chunks_built: int,
        embeddings_done: int,
        vectors_upserted: int,
        stage_ms: int,
        parse_ms: int = 0,
        chunk_ms: int = 0,
        embed_ms: int = 0,
        upsert_ms: int = 0,
    ) -> None:
        """上报阶段进度。"""

        if progress_callback is None:
            return
        progress_callback(
            stage,
            {
                "pages_parsed": pages_parsed,
                "chunks_built": chunks_built,
                "embeddings_done": embeddings_done,
                "vectors_upserted": vectors_upserted,
                "stage_ms": stage_ms,
                "parse_ms": parse_ms,
                "chunk_ms": chunk_ms,
                "embed_ms": embed_ms,
                "upsert_ms": upsert_ms,
            },
        )


class IngestCanceled(Exception):
    """入库取消异常（用于主动中断流程）。"""


def _parse_timestamp(value: str | None) -> int | None:
    """解析日期时间为 UTC 秒级时间戳。"""

    if value is None:
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
