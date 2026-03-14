from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from app.core.settings import Settings
from app.core.utils import utc_now_iso
from app.db.migrations import run_sqlite_migrations


@dataclass(slots=True)
class DatabaseConfig:
    path: Path


class Database:
    """SQLite 数据库封装，负责线程安全访问。"""

    def __init__(self, config: DatabaseConfig) -> None:
        self._path = config.path
        self._lock = Lock()
        self._connection = self._create_connection()

    def _create_connection(self) -> sqlite3.Connection:
        """创建数据库连接并启用外键约束。"""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        """执行写入语句。"""

        with self._lock:
            self._connection.execute(statement, params)
            self._connection.commit()

    def fetch_one(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        """查询单条记录。"""

        with self._lock:
            cursor = self._connection.execute(statement, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """查询多条记录。"""

        with self._lock:
            cursor = self._connection.execute(statement, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """关闭数据库连接，主要供测试重置使用。"""

        with self._lock:
            self._connection.close()


_database: Database | None = None


def get_database(settings: Settings) -> Database:
    """获取数据库单例。"""

    global _database
    if _database is None:
        config = DatabaseConfig(path=_parse_sqlite_path(settings.database_url))
        _database = Database(config)
    return _database


def init_database(settings: Settings) -> None:
    """初始化数据库结构，并补齐默认角色数据。"""

    database = get_database(settings)
    run_sqlite_migrations(database)
    _seed_default_roles(database)


def reset_database(settings: Settings) -> None:
    """清空数据库表数据，供测试环境复用。"""

    database = get_database(settings)
    run_sqlite_migrations(database)
    database.execute("DELETE FROM eval_result;")
    database.execute("DELETE FROM eval_run;")
    database.execute("DELETE FROM eval_item;")
    database.execute("DELETE FROM eval_set;")
    database.execute("DELETE FROM citation;")
    database.execute("DELETE FROM refresh_token;")
    database.execute("DELETE FROM kb_access;")
    database.execute("DELETE FROM user_role;")
    database.execute("DELETE FROM role;")
    database.execute("DELETE FROM user;")
    database.execute("DELETE FROM chat_run;")
    database.execute("DELETE FROM feedback;")
    database.execute("DELETE FROM message;")
    database.execute("DELETE FROM conversation;")
    database.execute("DELETE FROM ingest_job;")
    database.execute("DELETE FROM document;")
    database.execute("DELETE FROM knowledge_base;")
    _seed_default_roles(database)


def reset_database_singleton() -> None:
    """重置数据库单例，避免测试间共享连接状态。"""

    global _database
    if _database is not None:
        _database.close()
        _database = None


def _parse_sqlite_path(database_url: str) -> Path:
    """解析 SQLite 数据库路径。"""

    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError("当前仅支持 sqlite 数据库")
    path = parsed.path
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    if path.startswith("/") and not path.startswith("//"):
        path = path[1:]
    if not path:
        raise ValueError("数据库路径不能为空")
    return Path(path)


def _seed_default_roles(database: Database) -> None:
    """写入默认角色，并在权限变更时自动同步。"""

    from app.auth.permissions import DEFAULT_ROLE_PERMISSIONS

    for name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        permissions_json = json.dumps(permissions, ensure_ascii=False)
        exists = database.fetch_one(
            "SELECT role_id, permissions_json FROM role WHERE name = ?;",
            (name,),
        )
        if exists:
            if exists.get("permissions_json") != permissions_json:
                database.execute(
                    "UPDATE role SET permissions_json = ? WHERE name = ?;",
                    (permissions_json, name),
                )
            continue
        database.execute(
            """
            INSERT INTO role (role_id, name, permissions_json, created_at)
            VALUES (?, ?, ?, ?);
            """,
            (
                f"role_{name}",
                name,
                permissions_json,
                utc_now_iso(),
            ),
        )
