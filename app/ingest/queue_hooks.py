"""队列钩子与死信处理。"""

from __future__ import annotations

from rq import Queue
from rq.job import Job
from redis import Redis

from app.core.error_codes import ErrorCode
from app.core.logging import get_logger, log_event
from app.core.settings import get_settings
from app.ingest.worker_utils import build_document_service


def on_ingest_failure(
    job: Job,
    connection: Redis,
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback,
) -> None:
    """入库任务失败钩子。"""

    # RQ 1.16 会向失败回调传入 connection 参数。当前钩子仍从配置
    # 重新构造业务服务，connection 仅用于兼容 RQ 回调签名。
    _ = connection
    try:
        _handle_ingest_failure(job, exc_type, exc_value)
    except Exception as exc:
        logger = get_logger()
        log_event(
            logger,
            event="ingest_queue_failure_callback_error",
            fields={
                "job_id": getattr(job, "id", None),
                "queue": getattr(job, "origin", None),
                "error_message": f"{type(exc).__name__}: {exc}",
            },
        )


def _handle_ingest_failure(
    job: Job,
    exc_type: type[BaseException],
    exc_value: BaseException,
) -> None:
    """处理入库失败，异常由外层钩子吞掉以保护 worker。"""

    settings = get_settings()
    service = build_document_service(settings)
    doc_id, job_id, _request_id = job.args
    error_message = f"{exc_type.__name__}: {exc_value}"
    service.mark_job_failed(
        doc_id=doc_id,
        job_id=job_id,
        error_message=error_message,
        error_code=ErrorCode.INGEST_WORKER_FAILED.value,
    )
    logger = get_logger()
    log_event(
        logger,
        event="ingest_queue_failure",
        fields={
            "doc_id": doc_id,
            "job_id": job_id,
            "queue": job.origin,
            "error_message": error_message,
        },
    )
    if _should_move_to_dead(job):
        _move_to_dead(job, settings)
    _trim_dead_if_needed(settings)


def _should_move_to_dead(job: Job) -> bool:
    retries_left = getattr(job, "retries_left", None)
    if retries_left is None:
        return True
    return retries_left <= 0


def _move_to_dead(job: Job, settings) -> None:
    connection = Redis.from_url(settings.redis_url)
    dead_queue = Queue(settings.ingest_queue_dead_name, connection=connection)
    if job.origin == settings.ingest_queue_dead_name:
        return
    if job.id in dead_queue.get_job_ids():
        return
    dead_queue.enqueue_job(job)
    origin_queue = Queue(job.origin, connection=connection)
    try:
        origin_queue.failed_job_registry.remove(job, delete_job=False)
    except Exception:
        return


def _trim_dead_if_needed(settings) -> None:
    from app.ingest.queue_monitor import trim_dead_queue

    trim_dead_queue(settings)
