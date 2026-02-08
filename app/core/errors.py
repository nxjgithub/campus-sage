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
