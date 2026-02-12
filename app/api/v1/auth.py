"""认证相关路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import get_auth_service
from app.api.v1.schemas.auth import LoginRequest, LogoutRequest, LogoutResponse, RefreshRequest, TokenResponse
from app.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """用户登录。"""

    token_pair, _user, _roles = service.login(payload.email, payload.password)
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type="bearer",
        expires_in=token_pair.expires_in,
        request_id=request.state.request_id,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """刷新访问令牌。"""

    token_pair = service.refresh(payload.refresh_token)
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type="bearer",
        expires_in=token_pair.expires_in,
        request_id=request.state.request_id,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    payload: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    """注销刷新令牌。"""

    service.logout(payload.refresh_token)
    return LogoutResponse(status="ok", request_id=request.state.request_id)
