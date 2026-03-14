"""监控与运行时诊断接口。"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import require_permission
from app.api.v1.schemas.monitor import (
    QueueMoveDeadResponse,
    QueueStats,
    QueueStatsResponse,
    RuntimeDatabaseInfo,
    RuntimeDiagnosticsResponse,
    RuntimeSecurityInfo,
    RuntimeServicesInfo,
    RuntimeUploadInfo,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.core.settings import Settings, get_settings
from app.db.database import get_database
from app.db.migrations import get_current_schema_version
from app.ingest.queue_monitor import (
    check_queue_alerts,
    get_queue_stats,
    move_failed_to_dead,
)

router = APIRouter(prefix="/monitor", tags=["Monitor"])


@router.get("/queues", response_model=QueueStatsResponse)
def get_queues(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    settings: Settings = Depends(get_settings),
) -> QueueStatsResponse:
    """获取入库队列统计信息。"""

    stats = get_queue_stats(settings)
    alerts = check_queue_alerts(settings)
    return QueueStatsResponse(
        stats=QueueStats(**stats),
        alerts=alerts,
        request_id=request.state.request_id,
    )


@router.post("/queues/ingest/move-dead", response_model=QueueMoveDeadResponse)
def move_ingest_dead(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    settings: Settings = Depends(get_settings),
) -> QueueMoveDeadResponse:
    """将失败任务迁移至死信队列。"""

    moved = move_failed_to_dead(settings)
    return QueueMoveDeadResponse(moved=moved, request_id=request.state.request_id)


@router.get("/runtime", response_model=RuntimeDiagnosticsResponse)
def get_runtime_diagnostics(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    settings: Settings = Depends(get_settings),
) -> RuntimeDiagnosticsResponse:
    """返回当前运行时配置摘要，便于排查环境和配置问题。"""

    database = get_database(settings)
    parsed = urlparse(settings.database_url)
    target = parsed.path or parsed.netloc or settings.database_url
    if settings.database_backend == "sqlite" and target.startswith("/"):
        target = target.lstrip("/")
    return RuntimeDiagnosticsResponse(
        app_env=settings.app_env,
        log_level=settings.log_level,
        debug_mode=settings.debug_mode,
        enable_swagger=settings.enable_swagger,
        database=RuntimeDatabaseInfo(
            backend=settings.database_backend,
            target=target,
            schema_version=get_current_schema_version(database),
        ),
        services=RuntimeServicesInfo(
            vector_backend=settings.vector_backend,
            embedding_backend=settings.embedding_backend,
            vllm_enabled=settings.vllm_enabled,
            ingest_queue_enabled=settings.ingest_queue_enabled,
        ),
        upload=RuntimeUploadInfo(
            max_mb=settings.upload_max_mb,
            allowed_exts=list(settings.allowed_upload_extensions),
        ),
        security=RuntimeSecurityInfo(
            jwt_default_secret=settings.jwt_secret_key == "CHANGE_ME",
        ),
        warnings=settings.runtime_warnings(),
        request_id=request.state.request_id,
    )
