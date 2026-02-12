"""角色相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class RoleItem(BaseModel):
    """角色条目。"""

    name: str = Field(description="角色名称")
    permissions: list[str] = Field(description="权限列表")


class RoleListResponse(RequestIdMixin):
    """角色列表响应。"""

    items: list[RoleItem] = Field(description="角色列表")
