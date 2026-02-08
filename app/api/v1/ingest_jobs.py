"""入库任务相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.v1.deps import get_document_service
from app.api.v1.mappers import job_to_response
from app.api.v1.schemas.ingest import IngestJobDetailResponse
from app.core.settings import Settings, get_settings
from app.ingest.service import DocumentService
from app.ingest.queueing import enqueue_ingest_job

router = APIRouter(tags=["IngestJobs"])


@router.get("/ingest/jobs/{job_id}", response_model=IngestJobDetailResponse)
def get_ingest_job(
    request: Request, job_id: str, service: DocumentService = Depends(get_document_service)
) -> IngestJobDetailResponse:
    """获取入库任务详情。"""

    job = service.get_job(job_id)
    return IngestJobDetailResponse(
        **job_to_response(job).model_dump(),
        request_id=request.state.request_id,
    )


@router.post("/ingest/jobs/{job_id}/cancel", response_model=IngestJobDetailResponse)
def cancel_ingest_job(
    request: Request,
    job_id: str,
    service: DocumentService = Depends(get_document_service),
) -> IngestJobDetailResponse:
    """取消入库任务。"""

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
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> IngestJobDetailResponse:
    """重试入库任务（创建新任务）。"""

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
