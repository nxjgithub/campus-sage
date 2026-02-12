"""队列监控与死信处理。"""

from __future__ import annotations

from rq import Queue
from redis import Redis

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


def get_queue_stats(settings: Settings) -> dict[str, int]:
    """获取队列统计信息。"""

    try:
        connection = Redis.from_url(settings.redis_url)
        queue = Queue(settings.ingest_queue_name, connection=connection)
        dead_queue = Queue(settings.ingest_queue_dead_name, connection=connection)
        return {
            "queued": queue.count,
            "started": queue.started_job_registry.count,
            "deferred": queue.deferred_job_registry.count,
            "finished": queue.finished_job_registry.count,
            "failed_registry": queue.failed_job_registry.count,
            "dead": dead_queue.count,
            "scheduled": queue.scheduled_job_registry.count,
        }
    except Exception as exc:
        raise AppError(
            code=ErrorCode.INGEST_QUEUE_UNAVAILABLE,
            message="入库队列不可用",
            detail={"error": str(exc)},
            status_code=503,
        ) from exc


def move_failed_to_dead(settings: Settings) -> int:
    """将失败队列的任务移动到死信队列。"""

    try:
        connection = Redis.from_url(settings.redis_url)
        origin_queue = Queue(settings.ingest_queue_name, connection=connection)
        failed_registry = origin_queue.failed_job_registry
        dead_queue = Queue(settings.ingest_queue_dead_name, connection=connection)
        moved = 0
        for job_id in failed_registry.get_job_ids():
            if job_id in dead_queue.get_job_ids():
                continue
            job = origin_queue.fetch_job(job_id)
            if job is None:
                continue
            dead_queue.enqueue_job(job)
            failed_registry.remove(job, delete_job=False)
            moved += 1
        trim_dead_queue(settings)
        return moved
    except Exception as exc:
        raise AppError(
            code=ErrorCode.INGEST_QUEUE_UNAVAILABLE,
            message="入库队列不可用",
            detail={"error": str(exc)},
            status_code=503,
        ) from exc


def check_queue_alerts(settings: Settings) -> list[str]:
    """根据阈值生成队列告警信息。"""

    stats = get_queue_stats(settings)
    alerts = []
    if stats["queued"] >= settings.ingest_queue_alert_threshold:
        alerts.append("入库队列积压超过阈值")
    if stats["failed_registry"] >= settings.ingest_queue_failed_alert_threshold:
        alerts.append("失败任务数量超过阈值")
    if stats["dead"] >= settings.ingest_queue_dead_max:
        alerts.append("死信队列数量超过上限")
    return alerts


def trim_dead_queue(settings: Settings) -> int:
    """裁剪死信队列，保留最近任务。"""

    connection = Redis.from_url(settings.redis_url)
    dead_queue = Queue(settings.ingest_queue_dead_name, connection=connection)
    job_ids = dead_queue.get_job_ids()
    if len(job_ids) <= settings.ingest_queue_dead_max:
        return 0
    to_remove = job_ids[: max(0, len(job_ids) - settings.ingest_queue_dead_max)]
    removed = 0
    for job_id in to_remove:
        job = dead_queue.fetch_job(job_id)
        if job is None:
            continue
        dead_queue.remove(job)
        removed += 1
    return removed
