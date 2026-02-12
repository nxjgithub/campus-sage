"""角色相关路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_user_service, require_permission
from app.api.v1.schemas.roles import RoleListResponse
from app.auth.dto import CurrentUser
from app.auth.permissions import Permission
from app.auth.service import UserService

router = APIRouter(tags=["Roles"])


@router.get("/roles", response_model=RoleListResponse)
def list_roles(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    service: UserService = Depends(get_user_service),
) -> RoleListResponse:
    """获取角色列表。"""

    items = []
    for role in service.list_all_roles():
        items.append(
            {"name": role.name, "permissions": _load_permissions(role.permissions_json)}
        )
    return RoleListResponse(items=items, request_id=request.state.request_id)


def _load_permissions(payload: str | None) -> list[str]:
    """解析权限列表。"""

    if not payload:
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]
