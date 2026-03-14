from __future__ import annotations

import logging

from fastapi import Request

from app.core.error_codes import ErrorCode
from app.core.errors import AppError, build_error_response


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


def test_build_error_response_logs_request_context(caplog) -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/kb/kb_missing",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    request = Request(scope)
    request.state.request_id = "req_test_error"

    with caplog.at_level(logging.WARNING, logger="csage"):
        response = build_error_response(
            request=request,
            code=ErrorCode.KB_NOT_FOUND,
            message="知识库不存在",
            detail={"kb_id": "kb_missing"},
            status_code=404,
        )

    assert response.status_code == 404
    assert "error_response" in caplog.text
    assert "req_test_error" in caplog.text
    assert "KB_NOT_FOUND" in caplog.text
