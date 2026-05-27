"""队列监控与死信处理。"""

from __future__ import annotations

import time

from rq import Queue
from redis import Redis

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


def _zset_count(connection: Redis, key: str) -> int:
    """直接读取有序集合数量，避免 RQ registry 统计时触发清理副作用。"""

    return int(connection.zcard(key) or 0)


def _zset_count_after_score(connection: Redis, key: str, min_score: float) -> int:
    """统计指定分数之后的有序集合成员，用于排除过期 started 记录。"""

    return int(connection.zcount(key, min_score, "+inf") or 0)


def _remove_zset_before_score(connection: Redis, key: str, max_score: float) -> int:
    """移除指定分数之前的有序集合成员。"""

    return int(connection.zremrangebyscore(key, "-inf", max_score) or 0)


def _queue_count(connection: Redis, key: str) -> int:
    """直接读取队列列表数量，保持监控接口只读。"""

    return int(connection.llen(key) or 0)


def get_queue_stats(settings: Settings) -> dict[str, int]:
    """获取队列统计信息。"""

    try:
        connection = Redis.from_url(settings.redis_url)
        queue = Queue(settings.ingest_queue_name, connection=connection)
        dead_queue = Queue(settings.ingest_queue_dead_name, connection=connection)
        now_ts = time.time()
        # RQ 的 registry.count/get_job_ids 会先 cleanup，可能在 Web 线程中触发
        # 失败回调并使用 signal，导致只读监控接口返回 503。这里直接读 Redis
        # 底层键数量，确保队列看板不改变任务状态。
        return {
            "queued": _queue_count(connection, queue.key),
            "started": _zset_count_after_score(connection, queue.started_job_registry.key, now_ts),
            "deferred": _zset_count(connection, queue.deferred_job_registry.key),
            "finished": _zset_count(connection, queue.finished_job_registry.key),
            "failed_registry": _zset_count(connection, queue.failed_job_registry.key),
            "dead": _queue_count(connection, dead_queue.key),
            "scheduled": _zset_count(connection, queue.scheduled_job_registry.key),
        }
    except Exception as exc:
        raise AppError(
            code=ErrorCode.INGEST_QUEUE_UNAVAILABLE,
            message="入库队列不可用",
            detail={"error": str(exc)},
            status_code=503,
        ) from exc


def cleanup_stale_started(settings: Settings) -> int:
    """清理过期 started registry 记录，不触碰任务本体。"""

    try:
        connection = Redis.from_url(settings.redis_url)
        queue = Queue(settings.ingest_queue_name, connection=connection)
        return _remove_zset_before_score(
            connection,
            queue.started_job_registry.key,
            time.time(),
        )
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
