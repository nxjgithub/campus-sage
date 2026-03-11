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
            source_uri TEXT,
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
    _try_add_column(database, "document", "source_uri", "TEXT")
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
            user_id TEXT,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    _try_add_column(database, "conversation", "user_id", "TEXT")
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
            next_steps_json TEXT,
            citations_json TEXT,
            parent_message_id TEXT,
            edited_from_message_id TEXT,
            sequence_no INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversation(conversation_id),
            FOREIGN KEY(parent_message_id) REFERENCES message(message_id),
            FOREIGN KEY(edited_from_message_id) REFERENCES message(message_id)
        );
        """
    )
    _try_add_column(database, "message", "next_steps_json", "TEXT")
    _try_add_column(database, "message", "parent_message_id", "TEXT")
    _try_add_column(database, "message", "edited_from_message_id", "TEXT")
    _try_add_column(database, "message", "sequence_no", "INTEGER")
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS citation (
            citation_row_id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            citation_id INTEGER NOT NULL,
            doc_id TEXT NOT NULL,
            doc_name TEXT NOT NULL,
            doc_version TEXT,
            published_at TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_path TEXT,
            chunk_id TEXT NOT NULL,
            snippet TEXT NOT NULL,
            score REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES message(message_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_citation_message_id
        ON citation(message_id);
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
        CREATE TABLE IF NOT EXISTS eval_set (
            eval_set_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_item (
            eval_item_id TEXT PRIMARY KEY,
            eval_set_id TEXT NOT NULL,
            question TEXT NOT NULL,
            gold_doc_id TEXT,
            gold_page_start INTEGER,
            gold_page_end INTEGER,
            tags_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(eval_set_id) REFERENCES eval_set(eval_set_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_item_set
        ON eval_item(eval_set_id);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_run (
            run_id TEXT PRIMARY KEY,
            eval_set_id TEXT NOT NULL,
            kb_id TEXT NOT NULL,
            topk INTEGER NOT NULL,
            threshold REAL,
            rerank_enabled INTEGER NOT NULL,
            metrics_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(eval_set_id) REFERENCES eval_set(eval_set_id),
            FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id)
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_result (
            run_result_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            eval_item_id TEXT NOT NULL,
            hit INTEGER NOT NULL,
            rank INTEGER,
            retrieve_ms INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES eval_run(run_id),
            FOREIGN KEY(eval_item_id) REFERENCES eval_item(eval_item_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_result_run
        ON eval_result(run_id);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS user (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_status
        ON user(status);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS role (
            role_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            permissions_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS user_role (
            user_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, role_id),
            FOREIGN KEY(user_id) REFERENCES user(user_id),
            FOREIGN KEY(role_id) REFERENCES role(role_id)
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_access (
            user_id TEXT NOT NULL,
            kb_id TEXT NOT NULL,
            access_level TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, kb_id),
            FOREIGN KEY(user_id) REFERENCES user(user_id),
            FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id)
        );
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_token (
            token_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY(user_id) REFERENCES user(user_id)
        );
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_token_user_id
        ON refresh_token(user_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kb_access_user_id
        ON kb_access(user_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kb_access_kb_id
        ON kb_access(kb_id);
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
        CREATE INDEX IF NOT EXISTS idx_conversation_user_id
        ON conversation(user_id);
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
        CREATE INDEX IF NOT EXISTS idx_message_conversation_sequence
        ON message(conversation_id, sequence_no);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_updated_at
        ON conversation(updated_at);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_feedback_message_id
        ON feedback(message_id);
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_run (
            run_id TEXT PRIMARY KEY,
            kb_id TEXT,
            user_id TEXT,
            conversation_id TEXT,
            user_message_id TEXT,
            assistant_message_id TEXT,
            status TEXT NOT NULL,
            cancel_flag INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            request_id TEXT,
            FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id),
            FOREIGN KEY(user_id) REFERENCES user(user_id),
            FOREIGN KEY(conversation_id) REFERENCES conversation(conversation_id),
            FOREIGN KEY(user_message_id) REFERENCES message(message_id),
            FOREIGN KEY(assistant_message_id) REFERENCES message(message_id)
        );
        """
    )
    _try_add_column(database, "chat_run", "kb_id", "TEXT")
    _try_add_column(database, "chat_run", "user_id", "TEXT")
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_run_conversation_id
        ON chat_run(conversation_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_run_kb_id
        ON chat_run(kb_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_run_user_id
        ON chat_run(user_id);
        """
    )
    database.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_run_status
        ON chat_run(status);
        """
    )
    _seed_default_roles(database)


def reset_database(settings: Settings) -> None:
    """清空数据库表数据（测试使用）。"""

    database = get_database(settings)
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


def _seed_default_roles(database: Database) -> None:
    """写入默认角色数据。"""

    from app.auth.permissions import DEFAULT_ROLE_PERMISSIONS
    import json

    from app.core.utils import utc_now_iso

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
