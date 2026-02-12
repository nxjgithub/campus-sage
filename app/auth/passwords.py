from __future__ import annotations

import re

from passlib.context import CryptContext

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


class PasswordHasher:
    """密码哈希与校验。"""

    def __init__(self, settings: Settings) -> None:
        self._context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        self._min_length = settings.password_min_length

    def hash_password(self, password: str) -> str:
        """生成密码哈希。"""

        self._validate(password)
        return self._context.hash(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        """校验密码是否一致。"""

        return self._context.verify(password, hashed)

    def _validate(self, password: str) -> None:
        """校验密码强度。"""

        if len(password) < self._min_length:
            raise AppError(
                code=ErrorCode.PASSWORD_TOO_WEAK,
                message="密码长度不足",
                detail={"min_length": self._min_length},
                status_code=400,
            )
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise AppError(
                code=ErrorCode.PASSWORD_TOO_WEAK,
                message="密码必须包含字母和数字",
                detail=None,
                status_code=400,
            )
