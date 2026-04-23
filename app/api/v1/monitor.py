"""监控与运行时诊断接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import require_permission
from app.api.v1.schemas.monitor import (
    QueueMoveDeadResponse,
    QueueStats,
    QueueStatsResponse,
    RuntimeDatabaseInfo,
    RuntimeDiagnosticsResponse,
    RuntimeRagMetricsInfo,
    RuntimeSecurityInfo,
    RuntimeServicesInfo,
    RuntimeUploadInfo,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.core.settings import Settings, get_settings
from app.db.database import get_database
from app.db.migrations import get_current_schema_version
from app.db.repos import RepositoryProvider
from app.ingest.queue_monitor import (
    check_queue_alerts,
    get_queue_stats,
    move_failed_to_dead,
)
from app.rag.runtime_metrics import build_rag_runtime_metrics

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
    provider = RepositoryProvider(database)
    runtime_messages = provider.conversation().list_recent_assistant_messages(limit=200)
    rag_metrics = build_rag_runtime_metrics(runtime_messages)
    return RuntimeDiagnosticsResponse(
        app_env=settings.app_env,
        log_level=settings.log_level,
        debug_mode=settings.debug_mode,
        enable_swagger=settings.enable_swagger,
        database=RuntimeDatabaseInfo(
            backend=settings.database_backend,
            target=settings.database_target,
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
            jwt_default_secret=settings.jwt_secret_is_default,
            jwt_weak_secret=settings.jwt_secret_is_weak,
        ),
        rag_metrics=RuntimeRagMetricsInfo(
            sample_size=rag_metrics.sample_size,
            refusal_count=rag_metrics.refusal_count,
            clarification_count=rag_metrics.clarification_count,
            freshness_warning_count=rag_metrics.freshness_warning_count,
            citation_covered_count=rag_metrics.citation_covered_count,
            refusal_rate=rag_metrics.refusal_rate,
            clarification_rate=rag_metrics.clarification_rate,
            freshness_warning_rate=rag_metrics.freshness_warning_rate,
            citation_coverage_rate=rag_metrics.citation_coverage_rate,
        ),
        warnings=settings.runtime_warnings(),
        request_id=request.state.request_id,
    )
