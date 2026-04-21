from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.core.settings import Settings
from app.core.utils import utc_now_iso
from app.db.migrations import run_mysql_migrations, run_sqlite_migrations


@dataclass(slots=True)
class DatabaseConfig:
    backend: str = "sqlite"
    path: Path | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    database_name: str | None = None
    charset: str = "utf8mb4"


class Database:
    """数据库封装，负责线程安全访问与多后端兼容。"""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._backend = config.backend
        self._path = config.path
        self._lock = Lock()
        self._connection = self._create_connection()
        self._integrity_error_types = self._resolve_integrity_error_types()

    @property
    def backend(self) -> str:
        """返回当前数据库后端名称。"""

        return self._backend

    def _create_connection(self) -> Any:
        """按后端类型创建数据库连接。"""

        if self._backend == "sqlite":
            return self._create_sqlite_connection()
        if self._backend == "mysql":
            return self._create_mysql_connection()
        raise ValueError(f"不支持的数据库后端：{self._backend}")

    def _create_sqlite_connection(self) -> sqlite3.Connection:
        """创建 SQLite 连接并启用外键约束。"""

        if self._path is None:
            raise ValueError("SQLite 数据库路径不能为空")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def _create_mysql_connection(self) -> Any:
        """创建 MySQL 连接，并确保字符集与当前契约一致。"""

        try:
            import pymysql  # type: ignore
        except ImportError as exc:
            raise RuntimeError("缺少 PyMySQL 依赖，请安装 pymysql 后再使用 MySQL。") from exc

        if not self._config.host or not self._config.username or not self._config.database_name:
            raise ValueError("MySQL 连接配置不完整")

        connection = pymysql.connect(
            host=self._config.host,
            port=self._config.port or 3306,
            user=self._config.username,
            password=self._config.password,
            database=self._config.database_name,
            charset=self._config.charset,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        with connection.cursor() as cursor:
            cursor.execute(f"SET NAMES {self._config.charset};")
        connection.commit()
        return connection

    def _resolve_integrity_error_types(self) -> tuple[type[BaseException], ...]:
        """返回当前后端对应的唯一性/外键完整性异常类型。"""

        if self._backend == "sqlite":
            return (sqlite3.IntegrityError,)
        if self._backend == "mysql":
            try:
                import pymysql  # type: ignore
            except ImportError:
                return ()
            return (pymysql.IntegrityError,)
        return ()

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        """执行写入语句。"""

        normalized_statement = self._normalize_statement(statement)
        with self._lock:
            try:
                if self._backend == "sqlite":
                    self._connection.execute(normalized_statement, params)
                else:
                    with self._connection.cursor() as cursor:
                        cursor.execute(normalized_statement, params)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def fetch_one(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        """查询单条记录。"""

        normalized_statement = self._normalize_statement(statement)
        with self._lock:
            if self._backend == "sqlite":
                cursor = self._connection.execute(normalized_statement, params)
                row = cursor.fetchone()
            else:
                with self._connection.cursor() as cursor:
                    cursor.execute(normalized_statement, params)
                    row = cursor.fetchone()
        if row is None:
            return None
        return dict(row) if not isinstance(row, dict) else row

    def fetch_all(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        """查询多条记录。"""

        normalized_statement = self._normalize_statement(statement)
        with self._lock:
            if self._backend == "sqlite":
                cursor = self._connection.execute(normalized_statement, params)
                rows = cursor.fetchall()
            else:
                with self._connection.cursor() as cursor:
                    cursor.execute(normalized_statement, params)
                    rows = cursor.fetchall()
        return [dict(row) if not isinstance(row, dict) else row for row in rows]

    def close(self) -> None:
        """关闭数据库连接，主要供测试重置使用。"""

        with self._lock:
            self._connection.close()

    def is_integrity_error(self, exc: BaseException) -> bool:
        """判断异常是否属于当前后端的约束冲突错误。"""

        return isinstance(exc, self._integrity_error_types)

    def _normalize_statement(self, statement: str) -> str:
        """按后端差异转换 SQL 占位符。"""

        if self._backend != "mysql":
            return statement
        return _convert_qmark_placeholders(statement)


_database: Database | None = None


def get_database(settings: Settings) -> Database:
    """获取数据库单例。"""

    global _database
    if _database is None:
        config = _parse_database_config(settings.database_url)
        _database = Database(config)
    return _database


def init_database(settings: Settings) -> None:
    """初始化数据库结构，并补齐默认角色数据。"""

    database = get_database(settings)
    _init_schema(database)
    _seed_default_roles(database)


def reset_database(settings: Settings) -> None:
    """清空数据库表数据，供测试环境复用。"""

    database = get_database(settings)
    _init_schema(database)
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


def _init_schema(database: Database) -> None:
    """按数据库后端初始化 schema。"""

    if database.backend == "sqlite":
        run_sqlite_migrations(database)
        return
    if database.backend == "mysql":
        run_mysql_migrations(database)
        return
    raise ValueError(f"不支持的数据库后端：{database.backend}")


def _parse_database_config(database_url: str) -> DatabaseConfig:
    """解析数据库连接串并生成统一配置。"""

    parsed = urlparse(database_url)
    if parsed.scheme == "sqlite":
        return DatabaseConfig(backend="sqlite", path=_parse_sqlite_path(database_url))
    if parsed.scheme.startswith("mysql"):
        return _parse_mysql_config(database_url)
    raise ValueError("当前仅支持 sqlite 或 mysql 数据库")


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


def _parse_mysql_config(database_url: str) -> DatabaseConfig:
    """解析 MySQL 数据库连接配置。"""

    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    if not parsed.hostname:
        raise ValueError("MySQL 主机不能为空")
    if not parsed.username:
        raise ValueError("MySQL 用户名不能为空")
    if not database_name:
        raise ValueError("MySQL 数据库名不能为空")
    query = parse_qs(parsed.query)
    charset = (query.get("charset") or ["utf8mb4"])[0] or "utf8mb4"
    return DatabaseConfig(
        backend="mysql",
        host=parsed.hostname,
        port=parsed.port or 3306,
        username=unquote(parsed.username),
        password=unquote(parsed.password) if parsed.password else None,
        database_name=database_name,
        charset=charset,
    )


def _convert_qmark_placeholders(statement: str) -> str:
    """将 SQLite 风格的问号占位符转换为 MySQL 风格。"""

    converted: list[str] = []
    in_single_quote = False
    in_double_quote = False
    escaped = False
    for char in statement:
        if char == "\\" and not escaped:
            escaped = True
            converted.append(char)
            continue
        if char == "'" and not in_double_quote and not escaped:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and not escaped:
            in_double_quote = not in_double_quote
        if char == "?" and not in_single_quote and not in_double_quote:
            converted.append("%s")
        else:
            converted.append(char)
        escaped = False
    return "".join(converted)


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
