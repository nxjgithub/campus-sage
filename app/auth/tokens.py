from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets

import jwt

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


@dataclass(slots=True)
class TokenPayload:
    """访问令牌载荷。"""

    user_id: str
    token_type: str


class TokenService:
    """JWT 令牌服务。"""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._issuer = settings.jwt_issuer
        self._access_minutes = settings.access_token_expire_minutes

    def create_access_token(self, user_id: str) -> tuple[str, int]:
        """创建访问令牌。"""

        expires_delta = timedelta(minutes=self._access_minutes)
        expires_at = datetime.now(timezone.utc) + expires_delta
        payload = {
            "sub": user_id,
            "type": "access",
            "iss": self._issuer,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, int(expires_delta.total_seconds())

    def decode_access_token(self, token: str) -> TokenPayload:
        """解析访问令牌。"""

        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._algorithm], issuer=self._issuer
            )
        except jwt.ExpiredSignatureError as exc:
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_EXPIRED,
                message="访问令牌已过期",
                detail=None,
                status_code=401,
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="访问令牌无效",
                detail=None,
                status_code=401,
            ) from exc
        if payload.get("type") != "access":
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="访问令牌类型不正确",
                detail=None,
                status_code=401,
            )
        user_id = payload.get("sub")
        if not user_id:
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="访问令牌缺少用户信息",
                detail=None,
                status_code=401,
            )
        return TokenPayload(user_id=str(user_id), token_type="access")

    @staticmethod
    def generate_refresh_token() -> str:
        """生成刷新令牌。"""

        return secrets.token_urlsafe(40)
