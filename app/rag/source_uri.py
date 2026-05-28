"""来源链接校验工具。"""

from __future__ import annotations

from urllib.parse import urlparse

_PLACEHOLDER_PATH_MARKERS = ("/demo/campus-sage",)


def is_official_source_uri(value: str | None) -> bool:
    """判断来源链接是否可作为用户可点击的官方来源。"""

    if value is None:
        return False
    candidate = value.strip()
    if not candidate:
        return False
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return False
    normalized_path = parsed.path.lower()
    return not any(marker in normalized_path for marker in _PLACEHOLDER_PATH_MARKERS)
