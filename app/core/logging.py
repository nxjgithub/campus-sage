from __future__ import annotations

import logging
from typing import Any


def get_logger(name: str = "csage") -> logging.Logger:
    """获取项目统一 logger。"""

    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, fields: dict[str, Any]) -> None:
    """输出结构化日志事件。"""

    payload = {"event": event, **fields}
    logger.info("%s", payload)
