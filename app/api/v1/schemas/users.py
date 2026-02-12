"""用户相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class UserCreateRequest(BaseModel):
    """创建用户请求。"""

    email: str = Field(description="邮箱")
    password: str = Field(description="密码")
    roles: list[str] | None = Field(default=None, description="角色列表")


class UserUpdateRequest(BaseModel):
    """更新用户请求。"""

    status: str | None = Field(default=None, description="账号状态")
    roles: list[str] | None = Field(default=None, description="角色列表")
    password: str | None = Field(default=None, description="重置密码")


class UserResponse(RequestIdMixin):
    """用户详情响应。"""

    user_id: str = Field(description="用户ID")
    email: str = Field(description="邮箱")
    status: str = Field(description="账号状态")
    roles: list[str] = Field(description="角色列表")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")
    last_login_at: str | None = Field(default=None, description="上次登录时间")


class UserListItem(BaseModel):
    """用户列表项。"""

    user_id: str = Field(description="用户ID")
    email: str = Field(description="邮箱")
    status: str = Field(description="账号状态")
    roles: list[str] = Field(description="角色列表")
    created_at: str = Field(description="创建时间")


class UserListResponse(RequestIdMixin):
    """用户列表响应。"""

    items: list[UserListItem] = Field(description="用户列表")
    total: int = Field(description="总数量")
    limit: int = Field(description="分页大小")
    offset: int = Field(description="分页偏移")


class KbAccessRequest(BaseModel):
    """知识库权限请求。"""

    kb_id: str = Field(description="知识库ID")
    access_level: str = Field(description="访问级别")


class KbAccessItem(BaseModel):
    """知识库权限条目。"""

    kb_id: str = Field(description="知识库ID")
    access_level: str = Field(description="访问级别")


class KbAccessResponse(RequestIdMixin):
    """知识库权限响应。"""

    user_id: str = Field(description="用户ID")
    items: list[KbAccessItem] = Field(description="权限列表")


class KbAccessBulkRequest(BaseModel):
    """知识库权限批量更新请求。"""

    items: list[KbAccessItem] = Field(description="权限列表")


class KbAccessDeleteResponse(RequestIdMixin):
    """知识库权限删除响应。"""

    user_id: str = Field(description="用户ID")
    kb_id: str = Field(description="知识库ID")
    status: str = Field(description="操作状态")
