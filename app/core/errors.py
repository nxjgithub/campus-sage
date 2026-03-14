from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.error_codes import ErrorCode
from app.core.logging import get_logger, log_event


@dataclass(slots=True)
class AppError(Exception):
    """业务异常，统一承载错误码与错误明细。"""

    code: ErrorCode
    message: str
    detail: dict[str, Any] | None = None
    status_code: int = 400

    def __post_init__(self) -> None:
        """显式初始化 Exception.args，确保 str(exc) 可用。"""

        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        """优先返回用户可读文案，并在存在明细时补充关键信息。"""

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
    """构建统一错误响应，并同步写入可检索日志。"""

    request_id = getattr(request.state, "request_id", None)
    _log_error_response(
        request=request,
        code=code,
        message=message,
        detail=detail,
        status_code=status_code,
        request_id=request_id,
    )
    payload = {
        "error": {"code": code, "message": message, "detail": detail},
        "request_id": request_id,
    }
    return JSONResponse(status_code=status_code, content=payload)


def _log_error_response(
    request: Request,
    code: ErrorCode,
    message: str,
    detail: dict[str, Any] | None,
    status_code: int,
    request_id: str | None,
) -> None:
    """记录统一错误响应日志，避免仅依赖堆栈定位失败请求。"""

    logger = get_logger()
    log_event(
        logger,
        event="error_response",
        level="error" if status_code >= 500 else "warning",
        fields={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "error_code": _normalize_error_code(code),
            "message": message,
            "detail_keys": sorted(detail.keys()) if isinstance(detail, dict) else [],
        },
    )


def _normalize_error_code(code: ErrorCode) -> str:
    """将错误码统一转换为字符串，便于日志检索。"""

    if isinstance(code, Enum):
        return str(code.value)
    return str(code)
