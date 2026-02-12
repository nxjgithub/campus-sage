"""认证相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import RequestIdMixin


class LoginRequest(BaseModel):
    """登录请求。"""

    email: str = Field(description="邮箱")
    password: str = Field(description="密码")


class TokenResponse(RequestIdMixin):
    """令牌响应。"""

    access_token: str = Field(description="访问令牌")
    refresh_token: str = Field(description="刷新令牌")
    token_type: str = Field(description="令牌类型")
    expires_in: int = Field(description="访问令牌有效期秒数")


class RefreshRequest(BaseModel):
    """刷新令牌请求。"""

    refresh_token: str = Field(description="刷新令牌")


class LogoutRequest(BaseModel):
    """退出登录请求。"""

    refresh_token: str = Field(description="刷新令牌")


class LogoutResponse(RequestIdMixin):
    """退出登录响应。"""

    status: str = Field(description="处理结果")
