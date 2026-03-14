from __future__ import annotations

import logging
from typing import Any


def get_logger(name: str = "csage") -> logging.Logger:
    """获取项目统一 logger。"""

    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    event: str,
    fields: dict[str, Any],
    level: str = "info",
) -> None:
    """输出结构化日志事件，并允许按级别写入。"""

    payload = {"event": event, **fields}
    log_method = getattr(logger, level, logger.info)
    log_method("%s", payload)
