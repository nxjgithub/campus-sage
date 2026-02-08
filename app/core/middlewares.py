from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Request, Response


async def request_id_middleware(request: Request, call_next: Callable[[Request], Response]) -> Response:
    """生成并注入 request_id，便于日志与错误响应关联。"""

    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
