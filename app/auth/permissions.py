from __future__ import annotations

import json

from app.db.models import RoleRecord


class Permission:
    """权限常量定义。"""

    KB_READ = "kb.read"
    KB_WRITE = "kb.write"
    DOC_READ = "doc.read"
    DOC_WRITE = "doc.write"
    INGEST_READ = "ingest.read"
    INGEST_WRITE = "ingest.write"
    RAG_ASK = "rag.ask"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_WRITE = "conversation.write"
    MESSAGE_WRITE = "message.write"
    FEEDBACK_WRITE = "feedback.write"
    USER_MANAGE = "user.manage"
    MONITOR_READ = "monitor.read"


DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["*"],
    "manager": [
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.DOC_READ,
        Permission.DOC_WRITE,
        Permission.INGEST_READ,
        Permission.INGEST_WRITE,
        Permission.RAG_ASK,
        Permission.CONVERSATION_READ,
        Permission.CONVERSATION_WRITE,
        Permission.MESSAGE_WRITE,
        Permission.FEEDBACK_WRITE,
        Permission.MONITOR_READ,
    ],
    "user": [
        Permission.KB_READ,
        Permission.RAG_ASK,
        Permission.CONVERSATION_READ,
        Permission.CONVERSATION_WRITE,
        Permission.MESSAGE_WRITE,
        Permission.FEEDBACK_WRITE,
    ],
}


def resolve_permissions(roles: list[RoleRecord]) -> set[str]:
    """解析角色权限集合。"""

    permissions: set[str] = set()
    for role in roles:
        perms = _load_permissions(role.permissions_json)
        if "*" in perms:
            return {"*"}
        permissions.update(perms)
    return permissions


def _load_permissions(payload: str | None) -> list[str]:
    """解析权限 JSON。"""

    if not payload:
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]
