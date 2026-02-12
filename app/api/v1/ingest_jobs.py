"""入库任务相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.v1.deps import get_authorization_service, get_document_service, get_kb_service, require_permission
from app.api.v1.mappers import job_to_response
from app.api.v1.schemas.ingest import IngestJobDetailResponse
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.settings import Settings, get_settings
from app.ingest.service import DocumentService
from app.ingest.queueing import enqueue_ingest_job
from app.ingest.service import KnowledgeBaseService

router = APIRouter(tags=["IngestJobs"])


@router.get("/ingest/jobs/{job_id}", response_model=IngestJobDetailResponse)
def get_ingest_job(
    request: Request,
    job_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.INGEST_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: DocumentService = Depends(get_document_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
) -> IngestJobDetailResponse:
    """获取入库任务详情。"""

    job = service.get_job(job_id)
    document = service.get_document(job.doc_id)
    kb_record = kb_service.get(document.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_record.kb_id,
        visibility=kb_record.visibility,
        required_level="read",
        allow_public=False,
    )
    return IngestJobDetailResponse(
        **job_to_response(job).model_dump(),
        request_id=request.state.request_id,
    )


@router.post("/ingest/jobs/{job_id}/cancel", response_model=IngestJobDetailResponse)
def cancel_ingest_job(
    request: Request,
    job_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.INGEST_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: DocumentService = Depends(get_document_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
) -> IngestJobDetailResponse:
    """取消入库任务。"""

    job = service.get_job(job_id)
    document = service.get_document(job.doc_id)
    kb_record = kb_service.get(document.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_record.kb_id,
        visibility=kb_record.visibility,
        required_level="write",
        allow_public=False,
    )
    job = service.cancel_job(job_id)
    return IngestJobDetailResponse(
        **job_to_response(job).model_dump(),
        request_id=request.state.request_id,
    )


@router.post("/ingest/jobs/{job_id}/retry", response_model=IngestJobDetailResponse)
def retry_ingest_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_permission(Permission.INGEST_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: DocumentService = Depends(get_document_service),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    settings: Settings = Depends(get_settings),
) -> IngestJobDetailResponse:
    """重试入库任务（创建新任务）。"""

    job = service.get_job(job_id)
    document = service.get_document(job.doc_id)
    kb_record = kb_service.get(document.kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=kb_record.kb_id,
        visibility=kb_record.visibility,
        required_level="write",
        allow_public=False,
    )
    job = service.retry_job(
        job_id,
        request_id=request.state.request_id,
    )
    queued = enqueue_ingest_job(job.doc_id, job.job_id, request.state.request_id, settings)
    if not queued:
        background_tasks.add_task(
            service.run_pipeline,
            job.doc_id,
            job.job_id,
            request.state.request_id,
        )
    return IngestJobDetailResponse(
        **job_to_response(job).model_dump(),
        request_id=request.state.request_id,
    )
