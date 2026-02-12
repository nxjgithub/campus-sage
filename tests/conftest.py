from __future__ import annotations

from pathlib import Path
import sys
from typing import Final
import os

import httpx
import redis


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


os.environ.setdefault("EMBEDDING_BACKEND", "simple")
os.environ.setdefault("VECTOR_BACKEND", "memory")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")


QDRANT_COLLECTIONS_PATH: Final[str] = "/collections"


def is_qdrant_backend() -> bool:
    return os.getenv("VECTOR_BACKEND", "memory") == "qdrant"


def is_qdrant_available() -> bool:
    if not is_qdrant_backend():
        return False
    base_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    try:
        response = httpx.get(f"{base_url}{QDRANT_COLLECTIONS_PATH}", timeout=1.0)
        return response.status_code == 200
    except Exception:
        return False


def is_redis_available() -> bool:
    base_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        client = redis.Redis.from_url(base_url)
        return bool(client.ping())
    except Exception:
        return False
