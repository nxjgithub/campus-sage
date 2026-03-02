from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.settings import Settings
from app.core.utils import new_id, utc_now_iso
from app.db.repos.interfaces import (
    DocumentRepositoryProtocol,
    IngestJobRepositoryProtocol,
    KnowledgeBaseRepositoryProtocol,
)
from app.db.models import DocumentRecord, IngestJobRecord, KnowledgeBaseRecord
from app.ingest.dto import PreparedDocument
from app.ingest.pipeline import IngestCanceled, IngestPipeline
from app.rag.vector_store import VectorStore, get_vector_store


class KnowledgeBaseService:
    """知识库管理服务（SQLite 实现）。"""

    def __init__(
        self,
        kb_repo: KnowledgeBaseRepositoryProtocol,
        doc_repo: DocumentRepositoryProtocol,
        job_repo: IngestJobRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._kb_repo = kb_repo
        self._doc_repo = doc_repo
        self._job_repo = job_repo
        self._settings = settings
        self._vector_store: VectorStore = get_vector_store(settings)

    def create(
        self, name: str, description: str | None, visibility: str, config: dict
    ) -> KnowledgeBaseRecord:
        """创建知识库。"""

        self._validate_config_consistency(config)
        kb_id = new_id("kb")
        now = utc_now_iso()
        record = KnowledgeBaseRecord(
            kb_id=kb_id,
            name=name,
            description=description,
            visibility=visibility,
            config=config,
            created_at=now,
            updated_at=now,
            deleted=False,
        )
        return self._kb_repo.create(record)

    def list_all(self) -> Iterable[KnowledgeBaseRecord]:
        """列出所有知识库。"""

        return self._kb_repo.list_all()

    def get(self, kb_id: str) -> KnowledgeBaseRecord:
        """获取知识库。"""

        record = self._kb_repo.get(kb_id)
        if record is None or record.deleted:
            raise AppError(
                code=ErrorCode.KB_NOT_FOUND,
                message="知识库不存在",
                detail={"kb_id": kb_id},
                status_code=404,
            )
        return record

    def update(
        self,
        kb_id: str,
        description: str | None,
        visibility: str | None,
        config: dict | None,
    ) -> KnowledgeBaseRecord:
        """更新知识库。"""

        record = self.get(kb_id)
        if description is not None:
            record.description = description
        if visibility is not None:
            record.visibility = visibility
        if config is not None:
            # 局部更新配置，避免 PATCH 时覆盖未传入字段。
            merged_config = dict(record.config or {})
            merged_config.update(config)
            self._validate_config_consistency(merged_config)
            record.config = merged_config
        record.updated_at = utc_now_iso()
        return self._kb_repo.update(record)

    def delete(self, kb_id: str) -> None:
        """逻辑删除知识库并清理向量。"""

        record = self.get(kb_id)
        record.deleted = True
        record.updated_at = utc_now_iso()
        self._kb_repo.update(record)
        self._job_repo.delete_by_kb_id(kb_id)
        self._doc_repo.mark_deleted_by_kb(kb_id=kb_id, updated_at=utc_now_iso())
        self._vector_store.delete_by_kb_id(kb_id)

    def default_config(self) -> dict:
        """生成默认配置。"""

        return {
            "topk": self._settings.rag_topk,
            "threshold": self._settings.rag_threshold,
            "rerank_enabled": self._settings.rerank_enabled,
            "max_context_tokens": self._settings.rag_max_context_tokens,
            "min_evidence_chunks": self._settings.rag_min_evidence_chunks,
            "min_context_chars": self._settings.rag_min_context_chars,
            "min_keyword_coverage": self._settings.rag_min_keyword_coverage,
        }

    def _validate_config_consistency(self, config: dict) -> None:
        """校验配置跨字段关系，避免保存不可执行的参数组合。"""

        topk = config.get("topk")
        min_evidence_chunks = config.get("min_evidence_chunks")
        if (
            isinstance(topk, int)
            and isinstance(min_evidence_chunks, int)
            and min_evidence_chunks > topk
        ):
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="知识库配置校验失败",
                detail={
                    "field": "min_evidence_chunks",
                    "reason": "must_not_exceed_topk",
                    "topk": topk,
                    "min_evidence_chunks": min_evidence_chunks,
                },
                status_code=400,
            )


class DocumentService:
    """文档与入库任务服务（SQLite 实现）。"""

    def __init__(
        self,
        doc_repo: DocumentRepositoryProtocol,
        job_repo: IngestJobRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._doc_repo = doc_repo
        self._job_repo = job_repo
        self._settings = settings
        self._pipeline = IngestPipeline(settings)
        self._vector_store: VectorStore = get_vector_store(settings)
        self._logger = get_logger()

    def prepare_document(
        self,
        kb_id: str,
        filename: str | None,
        doc_name: str | None,
        doc_version: str | None,
        published_at: str | None,
    ) -> PreparedDocument:
        """准备文档入库信息（不进行文件保存）。"""

        name = doc_name or filename or "document"
        extension = Path(filename or name).suffix.lower().lstrip(".")
        if extension not in self._allowed_exts():
            raise AppError(
                code=ErrorCode.FILE_TYPE_NOT_ALLOWED,
                message="文件类型不允许",
                detail={"ext": extension},
                status_code=400,
            )

        doc_id = new_id("doc")
        job_id = new_id("job")
        storage_path = Path(self._settings.storage_dir) / kb_id / f"{doc_id}.{extension}"
        return PreparedDocument(
            kb_id=kb_id,
            doc_id=doc_id,
            job_id=job_id,
            doc_name=name,
            doc_version=doc_version,
            published_at=published_at,
            storage_path=storage_path,
            extension=extension,
        )

    def create_document(
        self,
        prepared: PreparedDocument,
        file_size_bytes: int,
        request_id: str | None,
    ) -> tuple[DocumentRecord, IngestJobRecord]:
        """创建文档与入库任务记录。"""

        if file_size_bytes > self._settings.upload_max_mb * 1024 * 1024:
            raise AppError(
                code=ErrorCode.FILE_TOO_LARGE,
                message="文件大小超过限制",
                detail={"max_mb": self._settings.upload_max_mb},
                status_code=400,
            )

        now = utc_now_iso()
        document = DocumentRecord(
            doc_id=prepared.doc_id,
            kb_id=prepared.kb_id,
            doc_name=prepared.doc_name,
            doc_version=prepared.doc_version,
            published_at=prepared.published_at,
            status="processing",
            error_message=None,
            chunk_count=0,
            file_path=str(prepared.storage_path),
            created_at=now,
            updated_at=now,
            deleted=False,
        )
        job = IngestJobRecord(
            job_id=prepared.job_id,
            kb_id=prepared.kb_id,
            doc_id=prepared.doc_id,
            status="queued",
            progress=None,
            error_message=None,
            error_code=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        self._doc_repo.create(document)
        self._job_repo.create(job)

        return document, job

    def list_documents(self, kb_id: str) -> Iterable[DocumentRecord]:
        """列出知识库下文档。"""

        return self._doc_repo.list_by_kb(kb_id)

    def get_document(self, doc_id: str) -> DocumentRecord:
        """获取文档。"""

        record = self._doc_repo.get(doc_id)
        if record is None or record.deleted:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="文档不存在",
                detail={"doc_id": doc_id},
                status_code=404,
            )
        return record

    def delete_document(self, doc_id: str) -> DocumentRecord:
        """逻辑删除文档并清理向量。"""

        record = self.get_document(doc_id)
        record.deleted = True
        record.status = "deleted"
        record.updated_at = utc_now_iso()
        self._doc_repo.update(record)
        self._job_repo.delete_by_doc_id(doc_id)
        self._vector_store.delete_by_doc_id(kb_id=record.kb_id, doc_id=record.doc_id)
        if record.file_path:
            try:
                Path(record.file_path).unlink(missing_ok=True)
            except Exception as exc:
                log_event(
                    self._logger,
                    event="storage_cleanup_failed",
                    fields={
                        "doc_id": record.doc_id,
                        "kb_id": record.kb_id,
                        "path": record.file_path,
                        "error": str(exc),
                    },
                )
        return record

    def reindex(
        self,
        doc_id: str,
        request_id: str | None,
    ) -> IngestJobRecord:
        """重新入库（生成新任务）。"""

        record = self.get_document(doc_id)
        job_id = new_id("job")
        now = utc_now_iso()
        job = IngestJobRecord(
            job_id=job_id,
            kb_id=record.kb_id,
            doc_id=record.doc_id,
            status="queued",
            progress=None,
            error_message=None,
            error_code=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        self._job_repo.create(job)
        return job

    def get_job(self, job_id: str) -> IngestJobRecord:
        """获取入库任务。"""

        record = self._job_repo.get(job_id)
        if record is None:
            raise AppError(
                code=ErrorCode.INGEST_JOB_NOT_FOUND,
                message="入库任务不存在",
                detail={"job_id": job_id},
                status_code=404,
            )
        return record

    def cancel_job(self, job_id: str) -> IngestJobRecord:
        """取消入库任务。"""

        job = self.get_job(job_id)
        if job.status in {"succeeded", "failed", "canceled"}:
            return job
        job.status = "canceled"
        job.error_message = "入库已取消"
        job.error_code = ErrorCode.INGEST_CANCELED.value
        job.progress = self._with_stage(job.progress, "canceled")
        job.finished_at = utc_now_iso()
        job.updated_at = utc_now_iso()
        self._job_repo.update(job)

        document = self._doc_repo.get(job.doc_id)
        if document and not document.deleted:
            document.status = "failed"
            document.error_message = "入库已取消"
            document.updated_at = utc_now_iso()
            self._doc_repo.update(document)
            self._vector_store.delete_by_doc_id(
                kb_id=document.kb_id, doc_id=document.doc_id
            )
        return job

    def retry_job(
        self,
        job_id: str,
        request_id: str | None,
    ) -> IngestJobRecord:
        """重试入库任务（创建新任务）。"""

        job = self.get_job(job_id)
        if job.status not in {"failed", "canceled"}:
            raise AppError(
                code=ErrorCode.INGEST_JOB_NOT_RETRYABLE,
                message="任务状态不允许重试",
                detail={"job_id": job_id, "status": job.status},
                status_code=409,
            )
        document = self.get_document(job.doc_id)
        document.status = "processing"
        document.error_message = None
        document.chunk_count = 0
        document.updated_at = utc_now_iso()
        self._doc_repo.update(document)

        new_job_id = new_id("job")
        now = utc_now_iso()
        new_job = IngestJobRecord(
            job_id=new_job_id,
            kb_id=document.kb_id,
            doc_id=document.doc_id,
            status="queued",
            progress=None,
            error_message=None,
            error_code=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        self._job_repo.create(new_job)
        return new_job

    def _allowed_exts(self) -> set[str]:
        """解析允许的文件后缀。"""

        return {
            ext.strip().lower()
            for ext in self._settings.upload_allowed_exts.split(",")
            if ext.strip()
        }

    def _build_progress(
        self,
        stage: str,
        pages_parsed: int,
        chunks_built: int,
        embeddings_done: int,
        vectors_upserted: int,
        stage_ms: int = 0,
        parse_ms: int = 0,
        chunk_ms: int = 0,
        embed_ms: int = 0,
        upsert_ms: int = 0,
    ) -> dict[str, object]:
        """构建阶段进度信息。"""

        return {
            "stage": stage,
            "pages_parsed": pages_parsed,
            "chunks_built": chunks_built,
            "embeddings_done": embeddings_done,
            "vectors_upserted": vectors_upserted,
            "stage_ms": stage_ms,
            "parse_ms": parse_ms,
            "chunk_ms": chunk_ms,
            "embed_ms": embed_ms,
            "upsert_ms": upsert_ms,
        }

    def _with_stage(self, progress: dict[str, object] | None, stage: str) -> dict[str, object]:
        """在已有进度上更新阶段。"""

        if progress is None:
            return self._build_progress(stage, 0, 0, 0, 0)
        updated = dict(progress)
        updated["stage"] = stage
        return updated

    def run_pipeline(self, doc_id: str, job_id: str, request_id: str | None) -> None:
        """执行入库流程并更新状态。"""

        document = self._doc_repo.get(doc_id)
        job = self._job_repo.get(job_id)
        if document is None or job is None:
            return
        if document.deleted:
            job.status = "canceled"
            job.updated_at = utc_now_iso()
            job.error_code = ErrorCode.INGEST_CANCELED.value
            job.progress = self._build_progress("canceled", 0, 0, 0, 0)
            job.finished_at = utc_now_iso()
            self._job_repo.update(job)
            return
        file_path = Path(document.file_path) if document.file_path else None
        if file_path is None or not file_path.exists():
            document.status = "failed"
            document.error_message = "入库文件不存在"
            document.updated_at = utc_now_iso()
            job.status = "failed"
            job.error_message = "入库文件不存在"
            job.error_code = ErrorCode.INGEST_PARSE_FAILED.value
            job.progress = self._with_stage(job.progress, "failed")
            job.finished_at = utc_now_iso()
            job.updated_at = utc_now_iso()
            self._doc_repo.update(document)
            self._job_repo.update(job)
            log_event(
                self._logger,
                event="ingest",
                fields={
                    "request_id": request_id,
                    "kb_id": document.kb_id,
                    "doc_id": document.doc_id,
                    "chunk_count": 0,
                    "embed_count": 0,
                    "upsert_count": 0,
                    "pages": 0,
                    "parse_ms": 0,
                    "chunk_ms": 0,
                    "embed_ms": 0,
                    "upsert_ms": 0,
                    "total_ms": 0,
                    "job_status": job.status,
                    "error_message": "入库文件不存在",
                },
            )
            return

        job.status = "running"
        job.updated_at = utc_now_iso()
        job.error_code = None
        job.progress = self._build_progress("running", 0, 0, 0, 0)
        job.started_at = utc_now_iso()
        job.finished_at = None
        self._job_repo.update(job)

        result = None
        error_message = None

        def progress_callback(stage: str, metrics: dict[str, int]) -> None:
            current_job = self._job_repo.get(job_id)
            if current_job is None or current_job.status == "canceled":
                return
            current_job.progress = self._build_progress(
                stage=stage,
                pages_parsed=metrics.get("pages_parsed", 0),
                chunks_built=metrics.get("chunks_built", 0),
                embeddings_done=metrics.get("embeddings_done", 0),
                vectors_upserted=metrics.get("vectors_upserted", 0),
                stage_ms=metrics.get("stage_ms", 0),
                parse_ms=metrics.get("parse_ms", 0),
                chunk_ms=metrics.get("chunk_ms", 0),
                embed_ms=metrics.get("embed_ms", 0),
                upsert_ms=metrics.get("upsert_ms", 0),
            )
            current_job.updated_at = utc_now_iso()
            self._job_repo.update(current_job)

        def is_canceled() -> bool:
            current_job = self._job_repo.get(job_id)
            if current_job is None:
                return True
            return current_job.status == "canceled"

        try:
            try:
                self._vector_store.delete_by_doc_id(
                    kb_id=document.kb_id, doc_id=document.doc_id
                )
            except AppError as exc:
                # 删除旧向量是幂等清理动作，遇到瞬时断连时记录告警并继续主流程。
                log_event(
                    self._logger,
                    event="vector_cleanup_skipped",
                    fields={
                        "request_id": request_id,
                        "kb_id": document.kb_id,
                        "doc_id": document.doc_id,
                        "error_code": exc.code,
                        "error_message": exc.message,
                        "error_detail": exc.detail,
                    },
                )
            result = self._pipeline.run(
                kb_id=document.kb_id,
                doc_id=document.doc_id,
                doc_name=document.doc_name,
                doc_version=document.doc_version,
                published_at=document.published_at,
                file_path=document.file_path or "",
                cancel_checker=is_canceled,
                progress_callback=progress_callback,
            )
            refreshed_job = self._job_repo.get(job_id)
            if refreshed_job is None or refreshed_job.status == "canceled":
                self._vector_store.delete_by_doc_id(
                    kb_id=document.kb_id, doc_id=document.doc_id
                )
                return
            refreshed = self._doc_repo.get(doc_id)
            if refreshed is None or refreshed.deleted:
                job.status = "canceled"
                job.error_message = "文档已删除"
                job.error_code = ErrorCode.INGEST_CANCELED.value
                job.progress = self._with_stage(job.progress, "canceled")
                job.finished_at = utc_now_iso()
                job.updated_at = utc_now_iso()
                self._job_repo.update(job)
                self._vector_store.delete_by_doc_id(
                    kb_id=document.kb_id, doc_id=document.doc_id
                )
                return
            document.status = "indexed"
            document.chunk_count = result.chunk_count
            job.status = "succeeded"
            job.progress = {
                "stage": "done",
                "pages_parsed": result.pages_parsed,
                "chunks_built": result.chunk_count,
                "embeddings_done": result.embed_count,
                "vectors_upserted": result.upsert_count,
                "stage_ms": 0,
                "parse_ms": result.parse_ms,
                "chunk_ms": result.chunk_ms,
                "embed_ms": result.embed_ms,
                "upsert_ms": result.upsert_ms,
            }
            job.error_code = None
            job.finished_at = utc_now_iso()
        except IngestCanceled:
            latest_job = self._job_repo.get(job_id)
            if latest_job is not None:
                job.progress = latest_job.progress
            job.status = "canceled"
            job.error_message = "入库已取消"
            job.error_code = ErrorCode.INGEST_CANCELED.value
            job.progress = self._with_stage(job.progress, "canceled")
            document.status = "failed"
            document.error_message = "入库已取消"
            error_message = "入库已取消"
            job.finished_at = utc_now_iso()
            self._vector_store.delete_by_doc_id(
                kb_id=document.kb_id, doc_id=document.doc_id
            )
        except AppError as exc:
            latest_job = self._job_repo.get(job_id)
            if latest_job is not None:
                job.progress = latest_job.progress
            detail_error = None
            if exc.detail and isinstance(exc.detail.get("error"), str):
                detail_error = exc.detail["error"]
            source_message = None
            if exc.detail and isinstance(exc.detail.get("source_message"), str):
                source_message = exc.detail["source_message"]
            source_detail_error = None
            if exc.detail and isinstance(exc.detail.get("source_detail"), dict):
                source_detail = exc.detail["source_detail"]
                if isinstance(source_detail.get("error"), str):
                    source_detail_error = source_detail["error"]
            source_detail_field = None
            source_detail_actual_type = None
            source_detail_value_preview = None
            if exc.detail and isinstance(exc.detail.get("source_detail"), dict):
                source_detail = exc.detail["source_detail"]
                if isinstance(source_detail.get("field"), str):
                    source_detail_field = source_detail["field"]
                if isinstance(source_detail.get("actual_type"), str):
                    source_detail_actual_type = source_detail["actual_type"]
                if isinstance(source_detail.get("value_preview"), str):
                    source_detail_value_preview = source_detail["value_preview"]
            source_detail_message = None
            if exc.detail and isinstance(exc.detail.get("source_detail"), dict):
                source_detail = exc.detail["source_detail"]
                if isinstance(source_detail.get("body"), dict):
                    body = source_detail["body"]
                    if isinstance(body.get("message"), str):
                        source_detail_message = body["message"]
            error_text = exc.message if detail_error is None else f"{exc.message}: {detail_error}"
            if source_message:
                error_text = f"{exc.message}: {source_message}"
            if source_detail_error:
                error_text = f"{error_text} ({source_detail_error})"
            if source_detail_field:
                field_text = f"field={source_detail_field}"
                if source_detail_actual_type:
                    field_text = f"{field_text}, type={source_detail_actual_type}"
                if source_detail_value_preview:
                    field_text = f"{field_text}, value={source_detail_value_preview}"
                error_text = f"{error_text} ({field_text})"
            if source_detail_message:
                error_text = f"{error_text} ({source_detail_message})"
            document.status = "failed"
            document.error_message = error_text
            job.status = "failed"
            job.error_message = error_text
            job.error_code = exc.code.value
            job.progress = self._with_stage(job.progress, "failed")
            error_message = error_text
            job.finished_at = utc_now_iso()
        document.updated_at = utc_now_iso()
        job.updated_at = utc_now_iso()
        self._doc_repo.update(document)
        self._job_repo.update(job)

        log_event(
            self._logger,
            event="ingest",
            fields={
                "request_id": request_id,
                "kb_id": document.kb_id,
                "doc_id": document.doc_id,
                "chunk_count": result.chunk_count if result else 0,
                "embed_count": result.embed_count if result else 0,
                "upsert_count": result.upsert_count if result else 0,
                "pages": result.pages_parsed if result else 0,
                "parse_ms": result.parse_ms if result else 0,
                "chunk_ms": result.chunk_ms if result else 0,
                "embed_ms": result.embed_ms if result else 0,
                "upsert_ms": result.upsert_ms if result else 0,
                "total_ms": result.total_ms if result else 0,
                "job_status": job.status,
                "error_message": error_message,
            },
        )

    def mark_job_failed(
        self,
        doc_id: str,
        job_id: str,
        error_message: str,
        error_code: str,
        cleanup_vectors: bool = True,
    ) -> None:
        """标记入库任务失败并同步文档状态。"""

        job = self._job_repo.get(job_id)
        document = self._doc_repo.get(doc_id)
        if job is not None:
            job.status = "failed"
            job.error_message = error_message
            job.error_code = error_code
            job.progress = self._with_stage(job.progress, "failed")
            job.finished_at = utc_now_iso()
            job.updated_at = utc_now_iso()
            self._job_repo.update(job)
        if document is not None and not document.deleted:
            document.status = "failed"
            document.error_message = error_message
            document.updated_at = utc_now_iso()
            self._doc_repo.update(document)
            if cleanup_vectors:
                self._vector_store.delete_by_doc_id(
                    kb_id=document.kb_id, doc_id=document.doc_id
                )
