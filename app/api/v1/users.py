"""用户管理相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_current_user, get_user_service, require_permission
from app.api.v1.schemas.users import (
    KbAccessBulkRequest,
    KbAccessDeleteResponse,
    KbAccessRequest,
    KbAccessResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import UserService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_me(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """获取当前用户信息。"""

    roles = [role.name for role in service.list_roles(current_user.user.user_id)]
    return _user_response(current_user.user, roles, request.state.request_id)


@router.get("", response_model=UserListResponse)
def list_users(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> UserListResponse:
    """获取用户列表。"""

    items = []
    if limit <= 0 or limit > 200:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="分页大小非法",
            detail={"limit": limit},
            status_code=400,
        )
    if offset < 0:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="分页偏移非法",
            detail={"offset": offset},
            status_code=400,
        )
    if status is not None and status not in {"active", "disabled", "deleted"}:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="用户状态非法",
            detail={"status": status},
            status_code=400,
        )
    records, total = service.list_users(status, keyword, limit, offset)
    for record in records:
        roles = [role.name for role in service.list_roles(record.user_id)]
        items.append(
            {
                "user_id": record.user_id,
                "email": record.email,
                "status": record.status,
                "roles": roles,
                "created_at": record.created_at,
            }
        )
    return UserListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        request_id=request.state.request_id,
    )


@router.post("", response_model=UserResponse)
def create_user(
    request: Request,
    payload: UserCreateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """创建用户。"""

    roles = payload.roles or ["user"]
    record = service.create_user(payload.email, payload.password, roles)
    return _user_response(record, roles, request.state.request_id)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    request: Request,
    user_id: str,
    payload: UserUpdateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """更新用户。"""

    if payload.status is not None and payload.status not in {"active", "disabled", "deleted"}:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="用户状态非法",
            detail={"status": payload.status},
            status_code=400,
        )
    record = service.update_user(user_id, payload.status, payload.roles, payload.password)
    roles = [role.name for role in service.list_roles(record.user_id)]
    return _user_response(record, roles, request.state.request_id)


@router.post("/{user_id}/kb-access", response_model=KbAccessResponse)
def upsert_kb_access(
    request: Request,
    user_id: str,
    payload: KbAccessRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> KbAccessResponse:
    """设置用户知识库访问权限。"""

    if payload.access_level not in {"read", "write", "admin"}:
        raise AppError(
            code=ErrorCode.VALIDATION_FAILED,
            message="访问级别非法",
            detail={"access_level": payload.access_level},
            status_code=400,
        )
    service.get_user(user_id)
    access = service.upsert_kb_access(user_id, payload.kb_id, payload.access_level)
    return KbAccessResponse(
        user_id=user_id,
        items=[{"kb_id": access.kb_id, "access_level": access.access_level}],
        request_id=request.state.request_id,
    )


@router.get("/{user_id}/kb-access", response_model=KbAccessResponse)
def list_kb_access(
    request: Request,
    user_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> KbAccessResponse:
    """列出用户知识库权限。"""

    service.get_user(user_id)
    items = [
        {"kb_id": item.kb_id, "access_level": item.access_level}
        for item in service.list_kb_access(user_id)
    ]
    return KbAccessResponse(
        user_id=user_id,
        items=items,
        request_id=request.state.request_id,
    )


@router.delete(
    "/{user_id}/kb-access/{kb_id}", response_model=KbAccessDeleteResponse
)
def delete_kb_access(
    request: Request,
    user_id: str,
    kb_id: str,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> KbAccessDeleteResponse:
    """撤销用户知识库权限。"""

    service.get_user(user_id)
    removed = service.remove_kb_access(user_id, kb_id)
    if not removed:
        raise AppError(
            code=ErrorCode.KB_ACCESS_NOT_FOUND,
            message="权限记录不存在",
            detail={"user_id": user_id, "kb_id": kb_id},
            status_code=404,
        )
    return KbAccessDeleteResponse(
        user_id=user_id,
        kb_id=kb_id,
        status="deleted",
        request_id=request.state.request_id,
    )


@router.put("/{user_id}/kb-access", response_model=KbAccessResponse)
def replace_kb_access(
    request: Request,
    user_id: str,
    payload: KbAccessBulkRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> KbAccessResponse:
    """批量替换用户知识库权限。"""

    service.get_user(user_id)
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for item in payload.items:
        if item.access_level not in {"read", "write", "admin"}:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="访问级别非法",
                detail={"access_level": item.access_level},
                status_code=400,
            )
        if item.kb_id in seen:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="知识库ID重复",
                detail={"kb_id": item.kb_id},
                status_code=400,
            )
        seen.add(item.kb_id)
        items.append({"kb_id": item.kb_id, "access_level": item.access_level})
    records = service.replace_kb_access(user_id, items)
    response_items = [
        {"kb_id": record.kb_id, "access_level": record.access_level}
        for record in records
    ]
    return KbAccessResponse(
        user_id=user_id,
        items=response_items,
        request_id=request.state.request_id,
    )


def _user_response(record, roles: list[str], request_id: str | None) -> UserResponse:
    return UserResponse(
        user_id=record.user_id,
        email=record.email,
        status=record.status,
        roles=roles,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_login_at=record.last_login_at,
        request_id=request_id,
    )
