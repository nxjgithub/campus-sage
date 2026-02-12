from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_authorization_service, get_kb_service, require_permission
from app.api.v1.mappers import kb_to_list_item, kb_to_response
from app.api.v1.schemas.kb import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.errors import AppError
from app.ingest.service import KnowledgeBaseService

router = APIRouter(tags=["KnowledgeBase"])


@router.post("/kb", response_model=KnowledgeBaseResponse)
def create_kb(
    request: Request,
    payload: KnowledgeBaseCreateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_WRITE)),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseResponse:
    """创建知识库。"""

    config = (
        payload.config.model_dump(exclude_none=True)
        if payload.config
        else service.default_config()
    )
    record = service.create(
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
        config=config,
    )
    return kb_to_response(record, request.state.request_id)


@router.get("/kb", response_model=KnowledgeBaseListResponse)
def list_kb(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseListResponse:
    """获取知识库列表。"""

    items = []
    for record in service.list_all():
        try:
            authz.ensure_kb_access(
                current_user=current_user,
                kb_id=record.kb_id,
                visibility=record.visibility,
                required_level="read",
                allow_public=True,
            )
        except AppError:
            continue
        items.append(kb_to_list_item(record))
    return KnowledgeBaseListResponse(items=items, request_id=request.state.request_id)


@router.get("/kb/{kb_id}", response_model=KnowledgeBaseResponse)
def get_kb(
    request: Request,
    kb_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_READ)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseResponse:
    """获取知识库详情。"""

    record = service.get(kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=record.visibility,
        required_level="read",
        allow_public=True,
    )
    return kb_to_response(record, request.state.request_id)


@router.patch("/kb/{kb_id}", response_model=KnowledgeBaseResponse)
def update_kb(
    request: Request,
    kb_id: str,
    payload: KnowledgeBaseUpdateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeBaseResponse:
    """更新知识库信息与 RAG 参数。"""

    record = service.get(kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=record.visibility,
        required_level="write",
        allow_public=False,
    )
    config = payload.config.model_dump(exclude_none=True) if payload.config else None
    record = service.update(
        kb_id=kb_id,
        description=payload.description,
        visibility=payload.visibility,
        config=config,
    )
    return kb_to_response(record, request.state.request_id)


@router.delete("/kb/{kb_id}")
def delete_kb(
    request: Request,
    kb_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.KB_WRITE)),
    authz: AuthorizationService = Depends(get_authorization_service),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> dict:
    """删除知识库（逻辑删除并清理向量）。"""

    record = service.get(kb_id)
    authz.ensure_kb_access(
        current_user=current_user,
        kb_id=record.kb_id,
        visibility=record.visibility,
        required_level="write",
        allow_public=False,
    )
    service.delete(kb_id)
    return {"status": "deleted", "request_id": request.state.request_id}
