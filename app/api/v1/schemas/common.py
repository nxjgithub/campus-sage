"""通用 API Schema。"""

from pydantic import BaseModel, Field


class RequestIdMixin(BaseModel):
    """携带 request_id 的响应基类。"""

    request_id: str | None = Field(default=None, description="请求ID")
