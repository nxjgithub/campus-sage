"""入库任务执行入口（供 RQ Worker 调用）。"""

from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.settings import get_settings
from app.ingest.worker_utils import build_document_service


def run_ingest_job(doc_id: str, job_id: str, request_id: str | None) -> None:
    """执行入库任务。"""

    settings = get_settings()
    service = build_document_service(settings)
    try:
        service.run_pipeline(doc_id=doc_id, job_id=job_id, request_id=request_id)
    except Exception as exc:
        service.mark_job_failed(
            doc_id=doc_id,
            job_id=job_id,
            error_message=str(exc),
            error_code=ErrorCode.INGEST_WORKER_FAILED.value,
        )
        raise
