from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.utils import utc_now_iso


class DatabaseProtocol(Protocol):
    """定义迁移执行所需的最小数据库接口。"""

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None: ...

    def fetch_one(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> dict[str, object] | None: ...

    def fetch_all(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]: ...


@dataclass(frozen=True, slots=True)
class Migration:
    """描述单个 schema 迁移步骤。"""

    version: int
    name: str
    apply: Callable[[DatabaseProtocol], None]


def run_sqlite_migrations(database: DatabaseProtocol) -> None:
    """按版本顺序执行 SQLite schema 迁移。"""

    _ensure_migration_table(database)
    current_version = get_current_schema_version(database)
    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        migration.apply(database)
        database.execute(
            """
            INSERT INTO schema_migration (version, name, applied_at)
            VALUES (?, ?, ?);
            """,
            (migration.version, migration.name, utc_now_iso()),
        )


def run_mysql_migrations(database: DatabaseProtocol) -> None:
    """初始化 MySQL schema，并记录当前逻辑版本。"""

    _ensure_migration_table(database)
    current_version = get_current_schema_version(database)
    if current_version not in (0, LATEST_SCHEMA_VERSION):
        raise RuntimeError(
            "当前 MySQL schema 仅支持空库初始化或已初始化到最新版本；"
            "请使用新的数据库实例完成切换。"
        )
    _execute_many(database, MYSQL_BOOTSTRAP_STATEMENTS)
    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        database.execute(
            """
            INSERT INTO schema_migration (version, name, applied_at)
            VALUES (?, ?, ?);
            """,
            (migration.version, migration.name, utc_now_iso()),
        )


def get_current_schema_version(database: DatabaseProtocol) -> int:
    """读取当前 schema 版本，未初始化时返回 0。"""

    _ensure_migration_table(database)
    record = database.fetch_one(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migration;"
    )
    if record is None:
        return 0
    return int(record["version"])


def _ensure_migration_table(database: DatabaseProtocol) -> None:
    """确保 schema 迁移历史表存在。"""

    database.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )


def _migration_1_initial_core_schema(database: DatabaseProtocol) -> None:
    """创建最初的核心业务表结构。"""

    _execute_many(
        database,
        (
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
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_name
            ON knowledge_base(name);
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_document_kb_id
            ON document(kb_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_document_status
            ON document(status);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_document_published_at
            ON document(published_at);
            """,
            """
            CREATE TABLE IF NOT EXISTS ingest_job (
                job_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(kb_id) REFERENCES knowledge_base(kb_id),
                FOREIGN KEY(doc_id) REFERENCES document(doc_id)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ingest_job_kb_id
            ON ingest_job(kb_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ingest_job_doc_id
            ON ingest_job(doc_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS conversation (
                conversation_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_kb_id
            ON conversation(kb_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_updated_at
            ON conversation(updated_at);
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_message_conversation_id
            ON message(conversation_id);
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_citation_message_id
            ON citation(message_id);
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_feedback_message_id
            ON feedback(message_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS eval_set (
                eval_set_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            );
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_eval_item_set
            ON eval_item(eval_set_id);
            """,
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
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_eval_result_run
            ON eval_result(run_id);
            """,
        ),
    )


def _migration_2_extend_core_schema(database: DatabaseProtocol) -> None:
    """补齐核心表新增字段与相关索引。"""

    _ensure_column(database, "document", "source_uri", "TEXT")
    _ensure_column(database, "ingest_job", "error_code", "TEXT")
    _ensure_column(database, "ingest_job", "started_at", "TEXT")
    _ensure_column(database, "ingest_job", "finished_at", "TEXT")
    _ensure_column(database, "conversation", "user_id", "TEXT")
    _ensure_column(database, "message", "next_steps_json", "TEXT")
    _ensure_column(database, "message", "parent_message_id", "TEXT")
    _ensure_column(database, "message", "edited_from_message_id", "TEXT")
    _ensure_column(database, "message", "sequence_no", "INTEGER")
    _execute_many(
        database,
        (
            """
            CREATE INDEX IF NOT EXISTS idx_conversation_user_id
            ON conversation(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_message_conversation_sequence
            ON message(conversation_id, sequence_no);
            """,
        ),
    )


def _migration_3_add_auth_schema(database: DatabaseProtocol) -> None:
    """增加认证、RBAC 与知识库授权表。"""

    _execute_many(
        database,
        (
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_status
            ON user(status);
            """,
            """
            CREATE TABLE IF NOT EXISTS role (
                role_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                permissions_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_role (
                user_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY(user_id) REFERENCES user(user_id),
                FOREIGN KEY(role_id) REFERENCES role(role_id)
            );
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_kb_access_user_id
            ON kb_access(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_kb_access_kb_id
            ON kb_access(kb_id);
            """,
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_refresh_token_user_id
            ON refresh_token(user_id);
            """,
        ),
    )


def _migration_4_add_chat_run_schema(database: DatabaseProtocol) -> None:
    """增加会话运行跟踪表，并兼容旧表补列。"""

    _execute_many(
        database,
        (
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
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_run_conversation_id
            ON chat_run(conversation_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_run_kb_id
            ON chat_run(kb_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_run_user_id
            ON chat_run(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_run_status
            ON chat_run(status);
            """,
        ),
    )
    _ensure_column(database, "chat_run", "kb_id", "TEXT")
    _ensure_column(database, "chat_run", "user_id", "TEXT")


def _ensure_column(
    database: DatabaseProtocol, table: str, column: str, column_type: str
) -> None:
    """仅在列缺失时补齐，避免重复迁移报错。"""

    if not _table_exists(database, table):
        return
    if _column_exists(database, table, column):
        return
    database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")


def _table_exists(database: DatabaseProtocol, table: str) -> bool:
    """判断表是否存在。"""

    record = database.fetch_one(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?;
        """,
        (table,),
    )
    return record is not None


def _column_exists(database: DatabaseProtocol, table: str, column: str) -> bool:
    """判断表字段是否已存在。"""

    columns = database.fetch_all(f"PRAGMA table_info({table});")
    return any(item["name"] == column for item in columns)


def _execute_many(database: DatabaseProtocol, statements: tuple[str, ...]) -> None:
    """顺序执行多条 DDL 语句。"""

    for statement in statements:
        database.execute(statement)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial_core_schema", _migration_1_initial_core_schema),
    Migration(2, "extend_core_schema", _migration_2_extend_core_schema),
    Migration(3, "add_auth_schema", _migration_3_add_auth_schema),
    Migration(4, "add_chat_run_schema", _migration_4_add_chat_run_schema),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version

MYSQL_BOOTSTRAP_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS knowledge_base (
        kb_id VARCHAR(128) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description LONGTEXT NULL,
        visibility VARCHAR(32) NOT NULL,
        config_json LONGTEXT NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        deleted TINYINT(1) NOT NULL DEFAULT 0,
        UNIQUE KEY uq_knowledge_base_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS document (
        doc_id VARCHAR(128) PRIMARY KEY,
        kb_id VARCHAR(128) NOT NULL,
        doc_name VARCHAR(255) NOT NULL,
        doc_version VARCHAR(128) NULL,
        published_at VARCHAR(64) NULL,
        source_uri VARCHAR(1024) NULL,
        status VARCHAR(32) NOT NULL,
        error_message LONGTEXT NULL,
        chunk_count INT NOT NULL DEFAULT 0,
        file_path VARCHAR(1024) NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        deleted TINYINT(1) NOT NULL DEFAULT 0,
        KEY idx_document_kb_id (kb_id),
        KEY idx_document_status (status),
        KEY idx_document_published_at (published_at),
        CONSTRAINT fk_document_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_job (
        job_id VARCHAR(128) PRIMARY KEY,
        kb_id VARCHAR(128) NOT NULL,
        doc_id VARCHAR(128) NOT NULL,
        status VARCHAR(32) NOT NULL,
        progress_json LONGTEXT NULL,
        error_message LONGTEXT NULL,
        error_code VARCHAR(64) NULL,
        started_at VARCHAR(64) NULL,
        finished_at VARCHAR(64) NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        KEY idx_ingest_job_kb_id (kb_id),
        KEY idx_ingest_job_doc_id (doc_id),
        KEY idx_ingest_job_status (status),
        CONSTRAINT fk_ingest_job_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id),
        CONSTRAINT fk_ingest_job_doc
            FOREIGN KEY (doc_id) REFERENCES document(doc_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation (
        conversation_id VARCHAR(128) PRIMARY KEY,
        kb_id VARCHAR(128) NOT NULL,
        user_id VARCHAR(128) NULL,
        title VARCHAR(255) NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        deleted TINYINT(1) NOT NULL DEFAULT 0,
        KEY idx_conversation_kb_id (kb_id),
        KEY idx_conversation_user_id (user_id),
        KEY idx_conversation_updated_at (updated_at),
        CONSTRAINT fk_conversation_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS message (
        message_id VARCHAR(128) PRIMARY KEY,
        conversation_id VARCHAR(128) NOT NULL,
        role VARCHAR(32) NOT NULL,
        content LONGTEXT NOT NULL,
        refusal TINYINT(1) NOT NULL DEFAULT 0,
        refusal_reason VARCHAR(64) NULL,
        timing_json LONGTEXT NULL,
        next_steps_json LONGTEXT NULL,
        citations_json LONGTEXT NULL,
        parent_message_id VARCHAR(128) NULL,
        edited_from_message_id VARCHAR(128) NULL,
        sequence_no INT NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_message_conversation_id (conversation_id),
        KEY idx_message_conversation_sequence (conversation_id, sequence_no),
        KEY idx_message_role_created_at (role, created_at),
        CONSTRAINT fk_message_conversation
            FOREIGN KEY (conversation_id) REFERENCES conversation(conversation_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS citation (
        citation_row_id VARCHAR(128) PRIMARY KEY,
        message_id VARCHAR(128) NOT NULL,
        citation_id INT NOT NULL,
        doc_id VARCHAR(128) NOT NULL,
        doc_name VARCHAR(255) NOT NULL,
        doc_version VARCHAR(128) NULL,
        published_at VARCHAR(64) NULL,
        page_start INT NULL,
        page_end INT NULL,
        section_path VARCHAR(1024) NULL,
        chunk_id VARCHAR(128) NOT NULL,
        snippet LONGTEXT NOT NULL,
        score DOUBLE NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_citation_message_id (message_id),
        KEY idx_citation_doc_id (doc_id),
        CONSTRAINT fk_citation_message
            FOREIGN KEY (message_id) REFERENCES message(message_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id VARCHAR(128) PRIMARY KEY,
        message_id VARCHAR(128) NOT NULL,
        rating VARCHAR(32) NOT NULL,
        reasons_json LONGTEXT NULL,
        comment LONGTEXT NULL,
        expected_hint LONGTEXT NULL,
        status VARCHAR(32) NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_feedback_message_id (message_id),
        KEY idx_feedback_rating (rating),
        KEY idx_feedback_created_at (created_at),
        CONSTRAINT fk_feedback_message
            FOREIGN KEY (message_id) REFERENCES message(message_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_set (
        eval_set_id VARCHAR(128) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description LONGTEXT NULL,
        created_at VARCHAR(64) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_item (
        eval_item_id VARCHAR(128) PRIMARY KEY,
        eval_set_id VARCHAR(128) NOT NULL,
        question LONGTEXT NOT NULL,
        gold_doc_id VARCHAR(128) NULL,
        gold_page_start INT NULL,
        gold_page_end INT NULL,
        tags_json LONGTEXT NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_eval_item_set (eval_set_id),
        CONSTRAINT fk_eval_item_set
            FOREIGN KEY (eval_set_id) REFERENCES eval_set(eval_set_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_run (
        run_id VARCHAR(128) PRIMARY KEY,
        eval_set_id VARCHAR(128) NOT NULL,
        kb_id VARCHAR(128) NOT NULL,
        topk INT NOT NULL,
        threshold DOUBLE NULL,
        rerank_enabled TINYINT(1) NOT NULL DEFAULT 0,
        metrics_json LONGTEXT NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_eval_run_eval_set_id (eval_set_id),
        KEY idx_eval_run_kb_id (kb_id),
        CONSTRAINT fk_eval_run_set
            FOREIGN KEY (eval_set_id) REFERENCES eval_set(eval_set_id),
        CONSTRAINT fk_eval_run_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_result (
        run_result_id VARCHAR(128) PRIMARY KEY,
        run_id VARCHAR(128) NOT NULL,
        eval_item_id VARCHAR(128) NOT NULL,
        hit TINYINT(1) NOT NULL DEFAULT 0,
        `rank` INT NULL,
        retrieve_ms INT NULL,
        notes LONGTEXT NULL,
        created_at VARCHAR(64) NOT NULL,
        KEY idx_eval_result_run (run_id),
        KEY idx_eval_result_eval_item (eval_item_id),
        CONSTRAINT fk_eval_result_run
            FOREIGN KEY (run_id) REFERENCES eval_run(run_id),
        CONSTRAINT fk_eval_result_item
            FOREIGN KEY (eval_item_id) REFERENCES eval_item(eval_item_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS user (
        user_id VARCHAR(128) PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        last_login_at VARCHAR(64) NULL,
        UNIQUE KEY uq_user_email (email),
        KEY idx_user_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS role (
        role_id VARCHAR(128) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        permissions_json LONGTEXT NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        UNIQUE KEY uq_role_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS user_role (
        user_id VARCHAR(128) NOT NULL,
        role_id VARCHAR(128) NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        PRIMARY KEY (user_id, role_id),
        CONSTRAINT fk_user_role_user
            FOREIGN KEY (user_id) REFERENCES user(user_id),
        CONSTRAINT fk_user_role_role
            FOREIGN KEY (role_id) REFERENCES role(role_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_access (
        user_id VARCHAR(128) NOT NULL,
        kb_id VARCHAR(128) NOT NULL,
        access_level VARCHAR(32) NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        updated_at VARCHAR(64) NOT NULL,
        PRIMARY KEY (user_id, kb_id),
        KEY idx_kb_access_user_id (user_id),
        KEY idx_kb_access_kb_id (kb_id),
        CONSTRAINT fk_kb_access_user
            FOREIGN KEY (user_id) REFERENCES user(user_id),
        CONSTRAINT fk_kb_access_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_token (
        token_id VARCHAR(128) PRIMARY KEY,
        user_id VARCHAR(128) NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at VARCHAR(64) NOT NULL,
        revoked TINYINT(1) NOT NULL DEFAULT 0,
        created_at VARCHAR(64) NOT NULL,
        revoked_at VARCHAR(64) NULL,
        UNIQUE KEY uq_refresh_token_hash (token_hash),
        KEY idx_refresh_token_user_id (user_id),
        CONSTRAINT fk_refresh_token_user
            FOREIGN KEY (user_id) REFERENCES user(user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_run (
        run_id VARCHAR(128) PRIMARY KEY,
        kb_id VARCHAR(128) NULL,
        user_id VARCHAR(128) NULL,
        conversation_id VARCHAR(128) NULL,
        user_message_id VARCHAR(128) NULL,
        assistant_message_id VARCHAR(128) NULL,
        status VARCHAR(32) NOT NULL,
        cancel_flag TINYINT(1) NOT NULL DEFAULT 0,
        started_at VARCHAR(64) NOT NULL,
        finished_at VARCHAR(64) NULL,
        request_id VARCHAR(128) NULL,
        KEY idx_chat_run_conversation_id (conversation_id),
        KEY idx_chat_run_kb_id (kb_id),
        KEY idx_chat_run_user_id (user_id),
        KEY idx_chat_run_status (status),
        CONSTRAINT fk_chat_run_kb
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(kb_id),
        CONSTRAINT fk_chat_run_user
            FOREIGN KEY (user_id) REFERENCES user(user_id),
        CONSTRAINT fk_chat_run_conversation
            FOREIGN KEY (conversation_id) REFERENCES conversation(conversation_id),
        CONSTRAINT fk_chat_run_user_message
            FOREIGN KEY (user_message_id) REFERENCES message(message_id),
        CONSTRAINT fk_chat_run_assistant_message
            FOREIGN KEY (assistant_message_id) REFERENCES message(message_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
)
