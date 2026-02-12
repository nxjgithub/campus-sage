from __future__ import annotations

import argparse

from redis import Redis
from rq import Queue
from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from app.core.settings import get_settings


class CompatibleSimpleWorker(SimpleWorker):
    """Windows 兼容的 RQ Worker，使用线程定时器实现超时控制。"""

    death_penalty_class = TimerDeathPenalty


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="启动入库 RQ Worker（跨平台兼容）")
    parser.add_argument(
        "--queue",
        action="append",
        dest="queues",
        default=None,
        help="队列名称，可重复传入多次；默认读取 INGEST_QUEUE_NAME",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="处理完当前队列任务后退出（排障模式）",
    )
    parser.add_argument(
        "--with-scheduler",
        action="store_true",
        help="启用调度器轮询（通常可不启用）",
    )
    return parser.parse_args()


def main() -> None:
    """启动兼容 Worker。"""

    args = _parse_args()
    settings = get_settings()
    queue_names = args.queues or [settings.ingest_queue_name]

    connection = Redis.from_url(settings.redis_url)
    queues = [Queue(name, connection=connection) for name in queue_names]
    worker = CompatibleSimpleWorker(queues, connection=connection)
    worker.work(burst=args.burst, with_scheduler=args.with_scheduler)


if __name__ == "__main__":
    main()
