"""入库队列封装（RQ + Redis）。"""

from __future__ import annotations

from rq import Queue, Retry
from redis import Redis

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.ingest.queue_hooks import on_ingest_failure
from app.ingest.worker import run_ingest_job


def enqueue_ingest_job(
    doc_id: str,
    job_id: str,
    request_id: str | None,
    settings: Settings,
) -> bool:
    """入库任务入队，返回是否使用了队列。"""

    if not settings.ingest_queue_enabled:
        return False
    try:
        connection = Redis.from_url(settings.redis_url)
        queue = Queue(settings.ingest_queue_name, connection=connection)
        retry = Retry(
            max=settings.ingest_queue_retry_max,
            interval=settings.ingest_queue_retry_interval_s,
        )
        queue.enqueue(
            run_ingest_job,
            doc_id,
            job_id,
            request_id,
            job_timeout=settings.ingest_queue_timeout_s,
            ttl=settings.ingest_queue_ttl_s,
            result_ttl=settings.ingest_queue_result_ttl_s,
            failure_ttl=settings.ingest_queue_failure_ttl_s,
            retry=retry,
            on_failure=on_ingest_failure,
        )
        return True
    except Exception as exc:
        raise AppError(
            code=ErrorCode.INGEST_QUEUE_UNAVAILABLE,
            message="入库队列不可用",
            detail={"error": str(exc)},
            status_code=503,
        ) from exc
