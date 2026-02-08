from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from app.core.settings import Settings


@dataclass(slots=True)
class DatabaseConfig:
    path: Path


class Database:
    """SQLite 数据库封装（线程安全）。"""

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


_database: Database | None = None


def get_database(settings: Settings) -> Database:
    """获取数据库单例。"""

    global _database
    if _database is None:
        config = DatabaseConfig(path=_parse_sqlite_path(settings.database_url))
        _database = Database(config)
    return _database


def init_database(settings: Settings) -> None:
    """初始化数据库表结构。"""

    database = get_database(settings)
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_base (
            kb_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            visibility TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    database.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_name
        ON knowledge_base(name);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS document (
            doc_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            doc_name TEXT NOT NULL,
            doc_version TEXT,
            published_at TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            chunk_count INTEGER NOT NULL,
            file_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_kb_id
        ON document(kb_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_status
        ON document(status);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_published_at
        ON document(published_at);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_job (
            job_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_json TEXT,
            error_message TEXT,
            error_code TEXT,
            started_at TEXT,
            finished_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id),
            FOREIGN KEY(doc_id) REFERENCES document(doc_id)
        );
        """
    )
    _try_add_column(database, "ingest_job", "error_code", "TEXT")
    _try_add_column(database, "ingest_job", "started_at", "TEXT")
    _try_add_column(database, "ingest_job", "finished_at", "TEXT")
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_job_kb_id
        ON ingest_job(kb_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_job_doc_id
        ON ingest_job(doc_id);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation (
            conversation_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS message (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            refusal INTEGER NOT NULL,
            refusal_reason TEXT,
            timing_json TEXT,
            citations_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversation(conversation_id)
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            rating TEXT NOT NULL,
            reasons_json TEXT,
            comment TEXT,
            expected_hint TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES message(message_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_kb_id
        ON conversation(kb_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_conversation_id
        ON message(conversation_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_feedback_message_id
        ON feedback(message_id);
        """
    )


def reset_database(settings: Settings) -> None:
    """清空数据库表数据（测试使用）。"""

    database = get_database(settings)
    database.execute("DELETE FROM feedback;")
    database.execute("DELETE FROM message;")
    database.execute("DELETE FROM conversation;")
    database.execute("DELETE FROM ingest_job;")
    database.execute("DELETE FROM document;")
    database.execute("DELETE FROM knowledge_base;")


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


def _try_add_column(database: Database, table: str, column: str, column_type: str) -> None:
    """尝试追加列（用于已有库的兼容升级）。"""

    try:
        database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")
    except sqlite3.OperationalError:
        return
