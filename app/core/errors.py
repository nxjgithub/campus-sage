from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.error_codes import ErrorCode


@dataclass(slots=True)
class AppError(Exception):
    """业务异常（统一错误格式）。"""

    code: ErrorCode
    message: str
    detail: dict[str, Any] | None = None
    status_code: int = 400

    def __post_init__(self) -> None:
        """显式初始化 Exception.args，确保 str(exc) 可用。"""

        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        """优先返回可读主错误文案，并附加关键错误详情。"""

        if not isinstance(self.detail, dict):
            return self.message
        detail_error = self.detail.get("error")
        if isinstance(detail_error, str) and detail_error.strip():
            return f"{self.message}: {detail_error}"
        return self.message


def build_error_response(
    request: Request,
    code: ErrorCode,
    message: str,
    detail: dict[str, Any] | None,
    status_code: int,
) -> JSONResponse:
    """构建统一错误响应。"""

    request_id = getattr(request.state, "request_id", None)
    payload = {
        "error": {"code": code, "message": message, "detail": detail},
        "request_id": request_id,
    }
    return JSONResponse(status_code=status_code, content=payload)
