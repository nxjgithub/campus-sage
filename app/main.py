from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.error_codes import ErrorCode
from app.core.errors import AppError, build_error_response
from app.core.middlewares import request_id_middleware
from app.core.settings import get_settings
from app.db.database import init_database


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""

    settings = get_settings()
    docs_url = "/docs" if settings.enable_swagger else None
    redoc_url = "/redoc" if settings.enable_swagger else None
    app = FastAPI(
        title="CampusSage API",
        description=(
            "CampusSage（CSage）后端接口文档。"
            "所有接口遵循统一错误格式与 RAG 引用契约。"
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    init_database(settings)
    app.middleware("http")(request_id_middleware)
    app.include_router(api_router)
    _mount_rq_dashboard(app, settings)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return build_error_response(
            request=request,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return build_error_response(
            request=request,
            code=ErrorCode.VALIDATION_FAILED,
            message="入参校验失败",
            detail={"errors": exc.errors()},
            status_code=400,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.exception("未处理异常：%s", exc)
        return build_error_response(
            request=request,
            code=ErrorCode.UNEXPECTED_ERROR,
            message="服务内部错误",
            detail=None,
            status_code=500,
        )

    return app


def _mount_rq_dashboard(app: FastAPI, settings) -> None:
    """按需挂载 RQ Dashboard。"""

    if not settings.ingest_queue_dashboard_enabled:
        return
    try:
        from rq_dashboard import app as dashboard_app  # type: ignore
        from starlette.middleware.wsgi import WSGIMiddleware
    except Exception as exc:
        logging.exception("RQ Dashboard 加载失败：%s", exc)
        return
    dashboard_app.config["RQ_DASHBOARD_REDIS_URL"] = settings.redis_url
    app.mount("/rq-dashboard", WSGIMiddleware(dashboard_app))


app = create_app()
