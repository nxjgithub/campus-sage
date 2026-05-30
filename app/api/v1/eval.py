"""评测相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import (
    get_authorization_service,
    get_eval_service,
    get_kb_service,
    require_permission,
)
from app.api.v1.schemas.eval import (
    EvalMetrics,
    EvalCandidatePreviewResponse,
    EvalRunRequest,
    EvalRunItemResultListResponse,
    EvalRunItemResultResponse,
    EvalRunListItem,
    EvalRunListResponse,
    EvalRunResponse,
    EvalSetCreateRequest,
    EvalSetListItem,
    EvalSetListResponse,
    EvalSetResponse,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.settings import Settings, get_settings
from app.eval.service import EvalService
from app.ingest.service import KnowledgeBaseService

router = APIRouter(prefix="/eval", tags=["Eval"])


@router.get("/sets", response_model=EvalSetListResponse)
def list_eval_sets(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    service: EvalService = Depends(get_eval_service),
) -> EvalSetListResponse:
    """列出评测集。"""

    items = [
        EvalSetListItem(
            eval_set_id=record.eval_set_id,
            name=record.name,
            description=record.description,
            item_count=item_count,
            created_at=record.created_at,
        )
        for record, item_count in service.list_eval_sets()
    ]
    return EvalSetListResponse(items=items, request_id=request.state.request_id)


@router.post("/sets", response_model=EvalSetResponse)
def create_eval_set(
    request: Request,
    payload: EvalSetCreateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    service: EvalService = Depends(get_eval_service),
) -> EvalSetResponse:
    """创建评测集。"""

    record, items = service.create_eval_set(
        payload.name,
        payload.description,
        [item.model_dump() for item in payload.items],
    )
    return EvalSetResponse(
        eval_set_id=record.eval_set_id,
        name=record.name,
        description=record.description,
        item_count=len(items),
        created_at=record.created_at,
        request_id=request.state.request_id,
    )


@router.get("/runs", response_model=EvalRunListResponse)
def list_eval_runs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    service: EvalService = Depends(get_eval_service),
) -> EvalRunListResponse:
    """列出评测运行。"""

    items = [
        EvalRunListItem(
            run_id=record.run_id,
            eval_set_id=record.eval_set_id,
            kb_id=record.kb_id,
            topk=record.topk,
            threshold=record.threshold,
            rerank_enabled=record.rerank_enabled,
            metrics=_to_metrics(metrics),
            created_at=record.created_at,
        )
        for record, metrics in service.list_runs(limit=limit, offset=offset)
    ]
    return EvalRunListResponse(items=items, request_id=request.state.request_id)


@router.post("/runs", response_model=EvalRunResponse)
def run_eval(
    request: Request,
    payload: EvalRunRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    service: EvalService = Depends(get_eval_service),
    settings: Settings = Depends(get_settings),
) -> EvalRunResponse:
    """运行评测。"""

    kb_record = kb_service.get(payload.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    threshold = _resolve_eval_threshold(
        request_value=payload.threshold,
        kb_value=kb_record.config.get("threshold"),
        default_value=settings.rag_threshold,
    )
    rerank_enabled = _resolve_eval_rerank_enabled(
        request_value=payload.rerank_enabled,
        kb_value=kb_record.config.get("rerank_enabled"),
        default_value=settings.rerank_enabled,
    )
    run_record, metrics = service.run_eval(
        eval_set_id=payload.eval_set_id,
        kb_id=payload.kb_id,
        topk=payload.topk,
        threshold=threshold,
        rerank_enabled=rerank_enabled,
    )
    return EvalRunResponse(
        run_id=run_record.run_id,
        eval_set_id=run_record.eval_set_id,
        kb_id=run_record.kb_id,
        topk=run_record.topk,
        threshold=run_record.threshold,
        rerank_enabled=run_record.rerank_enabled,
        metrics=_to_metrics(metrics),
        created_at=run_record.created_at,
        request_id=request.state.request_id,
    )


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
def get_eval_run(
    request: Request,
    run_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    service: EvalService = Depends(get_eval_service),
) -> EvalRunResponse:
    """获取评测运行结果。"""

    record, metrics = service.get_run(run_id)
    return EvalRunResponse(
        run_id=record.run_id,
        eval_set_id=record.eval_set_id,
        kb_id=record.kb_id,
        topk=record.topk,
        threshold=record.threshold,
        rerank_enabled=record.rerank_enabled,
        metrics=_to_metrics(metrics),
        created_at=record.created_at,
        request_id=request.state.request_id,
    )


@router.get("/runs/{run_id}/results", response_model=EvalRunItemResultListResponse)
def get_eval_run_results(
    request: Request,
    run_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.MONITOR_READ)),
    service: EvalService = Depends(get_eval_service),
) -> EvalRunItemResultListResponse:
    """获取逐题评测结果。"""

    return EvalRunItemResultListResponse(
        items=[
            EvalRunItemResultResponse(
                eval_item_id=item.eval_item_id,
                question=item.question,
                gold_doc_id=item.gold_doc_id,
                gold_doc_name=item.gold_doc_name,
                hit=item.hit,
                rank=item.rank,
                retrieve_ms=item.retrieve_ms,
                raw_rank=item.raw_rank,
                threshold_rank=item.threshold_rank,
                raw_hit_count=item.raw_hit_count,
                threshold_hit_count=item.threshold_hit_count,
                final_hit_count=item.final_hit_count,
                top_candidates=[
                    EvalCandidatePreviewResponse(
                        rank=candidate.rank,
                        doc_id=candidate.doc_id,
                        doc_name=candidate.doc_name,
                        score=candidate.score,
                        matched=candidate.matched,
                    )
                    for candidate in item.top_candidates
                ],
            )
            for item in service.get_run_results(run_id)
        ],
        request_id=request.state.request_id,
    )


def _to_metrics(metrics: object) -> EvalMetrics | None:
    """转换评测指标输出。"""

    if metrics is None:
        return None
    if isinstance(metrics, EvalMetrics):
        return metrics
    return EvalMetrics(
        recall_at_k=metrics.recall_at_k,
        mrr=metrics.mrr,
        avg_ms=metrics.avg_ms,
        p95_ms=metrics.p95_ms,
        samples=metrics.samples,
    )


def _resolve_eval_threshold(
    request_value: float | None, kb_value: object, default_value: float
) -> float:
    """解析评测阈值，兼容历史脏配置并回退到默认值。"""

    if request_value is not None:
        return request_value
    if isinstance(kb_value, (int, float)):
        threshold = float(kb_value)
        if 0 <= threshold <= 1:
            return threshold
    return default_value


def _resolve_eval_rerank_enabled(
    request_value: bool | None, kb_value: object, default_value: bool
) -> bool:
    """解析评测重排开关，兼容历史脏配置并回退到默认值。"""

    if request_value is not None:
        return request_value
    if isinstance(kb_value, bool):
        return kb_value
    return default_value
