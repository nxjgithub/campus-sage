from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.errors import AppError


def test_app_error_str_uses_message_when_no_detail() -> None:
    exc = AppError(code=ErrorCode.UNEXPECTED_ERROR, message="系统异常")
    assert str(exc) == "系统异常"


def test_app_error_str_includes_detail_error() -> None:
    exc = AppError(
        code=ErrorCode.VECTOR_UPSERT_FAILED,
        message="向量写入失败",
        detail={"error": "Unexpected Response: 400"},
    )
    assert str(exc) == "向量写入失败: Unexpected Response: 400"
