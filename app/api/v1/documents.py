"""文档与入库相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile

from app.api.v1.deps import get_document_service, get_kb_service
from app.api.v1.mappers import doc_to_response, job_to_response
from app.api.v1.upload_utils import save_upload_file
from app.api.v1.schemas.documents import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.api.v1.schemas.ingest import IngestJobDetailResponse
from app.core.errors import AppError
from app.core.settings import Settings, get_settings
from app.ingest.service import DocumentService, KnowledgeBaseService
from app.ingest.queueing import enqueue_ingest_job

router = APIRouter(tags=["Documents"])


@router.post("/kb/{kb_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    kb_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_name: str | None = Form(default=None),
    doc_version: str | None = Form(default=None),
    published_at: str | None = Form(default=None),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    doc_service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    """上传文档并触发入库任务。"""

    kb_service.get(kb_id)
    prepared = doc_service.prepare_document(
        kb_id=kb_id,
        filename=file.filename,
        doc_name=doc_name,
        doc_version=doc_version,
        published_at=published_at,
    )
    max_bytes = settings.upload_max_mb * 1024 * 1024
    size = await save_upload_file(file, prepared.storage_path, max_bytes)
    try:
        doc_record, job_record = doc_service.create_document(
            prepared=prepared,
            file_size_bytes=size,
            request_id=request.state.request_id,
        )
    except AppError:
        prepared.storage_path.unlink(missing_ok=True)
        raise
    queued = enqueue_ingest_job(
        doc_record.doc_id,
        job_record.job_id,
        request.state.request_id,
        settings,
    )
    if not queued:
        background_tasks.add_task(
            doc_service.run_pipeline,
            doc_record.doc_id,
            job_record.job_id,
            request.state.request_id,
        )
    return DocumentUploadResponse(
        doc=doc_to_response(doc_record),
        job=job_to_response(job_record),
        request_id=request.state.request_id,
    )


@router.get("/kb/{kb_id}/documents", response_model=DocumentListResponse)
def list_documents(
    request: Request,
    kb_id: str,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    doc_service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    """获取知识库下的文档列表。"""

    kb_service.get(kb_id)
    items = [doc_to_response(record) for record in doc_service.list_documents(kb_id)]
    return DocumentListResponse(items=items, request_id=request.state.request_id)


@router.get("/documents/{doc_id}", response_model=DocumentDetailResponse)
def get_document(
    request: Request,
    doc_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentDetailResponse:
    """获取文档详情。"""

    record = service.get_document(doc_id)
    return DocumentDetailResponse(
        **doc_to_response(record).model_dump(),
        request_id=request.state.request_id,
    )


@router.delete("/documents/{doc_id}")
def delete_document(
    request: Request, doc_id: str, service: DocumentService = Depends(get_document_service)
) -> dict:
    """删除文档并清理向量与存储文件。"""

    service.delete_document(doc_id)
    return {"status": "deleted", "request_id": request.state.request_id}


@router.post("/documents/{doc_id}/reindex", response_model=IngestJobDetailResponse)
def reindex_document(
    request: Request,
    doc_id: str,
    background_tasks: BackgroundTasks,
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> IngestJobDetailResponse:
    """重新入库指定文档。"""

    job = service.reindex(
        doc_id,
        request_id=request.state.request_id,
    )
    queued = enqueue_ingest_job(doc_id, job.job_id, request.state.request_id, settings)
    if not queued:
        background_tasks.add_task(
            service.run_pipeline,
            doc_id,
            job.job_id,
            request.state.request_id,
        )
    return IngestJobDetailResponse(
        **job_to_response(job).model_dump(),
        request_id=request.state.request_id,
    )
