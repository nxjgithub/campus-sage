from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_kb_service
from app.api.v1.mappers import kb_to_list_item, kb_to_response
from app.api.v1.schemas.kb import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from app.ingest.service import KnowledgeBaseService

router = APIRouter(tags=["KnowledgeBase"])


@router.post("/kb", response_model=KnowledgeBaseResponse)
def create_kb(
    request: Request,
    payload: KnowledgeBaseCreateRequest,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseResponse:
    """创建知识库。"""

    config = payload.config.model_dump() if payload.config else service.default_config()
    record = service.create(
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
        config=config,
    )
    return kb_to_response(record, request.state.request_id)


@router.get("/kb", response_model=KnowledgeBaseListResponse)
def list_kb(
    request: Request, service: KnowledgeBaseService = Depends(get_kb_service)
) -> KnowledgeBaseListResponse:
    """获取知识库列表。"""

    items = [kb_to_list_item(record) for record in service.list_all()]
    return KnowledgeBaseListResponse(items=items, request_id=request.state.request_id)


@router.get("/kb/{kb_id}", response_model=KnowledgeBaseResponse)
def get_kb(
    request: Request, kb_id: str, service: KnowledgeBaseService = Depends(get_kb_service)
) -> KnowledgeBaseResponse:
    """获取知识库详情。"""

    record = service.get(kb_id)
    return kb_to_response(record, request.state.request_id)


@router.patch("/kb/{kb_id}", response_model=KnowledgeBaseResponse)
def update_kb(
    request: Request,
    kb_id: str,
    payload: KnowledgeBaseUpdateRequest,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseResponse:
    """更新知识库信息与 RAG 参数。"""

    config = payload.config.model_dump() if payload.config else None
    record = service.update(
        kb_id=kb_id,
        description=payload.description,
        visibility=payload.visibility,
        config=config,
    )
    return kb_to_response(record, request.state.request_id)


@router.delete("/kb/{kb_id}")
def delete_kb(
    request: Request, kb_id: str, service: KnowledgeBaseService = Depends(get_kb_service)
) -> dict:
    """删除知识库（逻辑删除并清理向量）。"""

    service.delete(kb_id)
    return {"status": "deleted", "request_id": request.state.request_id}
