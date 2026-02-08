from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO8601 字符串。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    """生成带前缀的业务 ID。"""

    return f"{prefix}_{uuid4().hex}"
