"""队列监控接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.settings import Settings, get_settings
from app.ingest.queue_monitor import (
    check_queue_alerts,
    get_queue_stats,
    move_failed_to_dead,
)

router = APIRouter(prefix="/api/v1/monitor", tags=["Monitor"])


@router.get("/queues")
def get_queues(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """获取队列统计信息。"""

    stats = get_queue_stats(settings)
    alerts = check_queue_alerts(settings)
    return {"stats": stats, "alerts": alerts, "request_id": request.state.request_id}


@router.post("/queues/ingest/move-dead")
def move_ingest_dead(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """将失败任务转入死信队列。"""

    moved = move_failed_to_dead(settings)
    return {"moved": moved, "request_id": request.state.request_id}
