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


@dataclass(frozen=True, slots=True)
class MysqlColumnComment:
    """描述 MySQL 字段注释所需的完整列定义。"""

    definition: str
    comment: str


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
    _ensure_sqlite_compatibility(database)


def run_mysql_migrations(database: DatabaseProtocol) -> None:
    """初始化 MySQL schema，并记录当前逻辑版本。"""

    _ensure_migration_table(database)
    current_version = get_current_schema_version(database)
    allowed_versions = {0, MYSQL_COMMENT_BASE_SCHEMA_VERSION, LATEST_SCHEMA_VERSION}
    if current_version not in allowed_versions:
        raise RuntimeError(
            "当前 MySQL schema 仅支持空库初始化或已初始化到最新版本；"
            "请使用新的数据库实例完成切换。"
        )
    _execute_many(database, MYSQL_BOOTSTRAP_STATEMENTS)
    _ensure_mysql_compatibility(database)
    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        if migration.version == MYSQL_COMMENT_SCHEMA_VERSION:
            _apply_mysql_schema_comments(database)
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
                suggestions_json TEXT,
                citations_json TEXT,
                created_at TEXT NOT NULL,
                request_id TEXT,
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
    _ensure_column(database, "message", "suggestions_json", "TEXT")
    _ensure_column(database, "message", "parent_message_id", "TEXT")
    _ensure_column(database, "message", "edited_from_message_id", "TEXT")
    _ensure_column(database, "message", "sequence_no", "INTEGER")
    _ensure_column(database, "message", "request_id", "TEXT")
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


def _migration_5_add_mysql_schema_comments(database: DatabaseProtocol) -> None:
    """占位记录 MySQL 注释版本；SQLite 无同等元数据能力。"""

    return None


def _ensure_sqlite_compatibility(database: DatabaseProtocol) -> None:
    """补齐 SQLite 运行时必需字段，兼容旧版本数据库。"""

    _ensure_column(database, "message", "suggestions_json", "TEXT")
    _ensure_column(database, "message", "request_id", "TEXT")


def _ensure_mysql_compatibility(database: DatabaseProtocol) -> None:
    """补齐 MySQL 运行时必需字段，兼容旧版本数据库。"""

    _ensure_mysql_column(database, "message", "suggestions_json", "LONGTEXT NULL")
    _ensure_mysql_column(database, "message", "request_id", "VARCHAR(128) NULL")


def _ensure_column(
    database: DatabaseProtocol, table: str, column: str, column_type: str
) -> None:
    """仅在列缺失时补齐，避免重复迁移报错。"""

    if not _table_exists(database, table):
        return
    if _column_exists(database, table, column):
        return
    database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")


def _ensure_mysql_column(
    database: DatabaseProtocol, table: str, column: str, column_type: str
) -> None:
    """仅在 MySQL 列缺失时补齐，避免旧库启动后接口字段缺失。"""

    record = database.fetch_one(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = ?
          AND COLUMN_NAME = ?;
        """,
        (table, column),
    )
    if record is not None:
        return
    database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")


def _apply_mysql_schema_comments(database: DatabaseProtocol) -> None:
    """为 MySQL 表和字段写入中文 COMMENT 元数据。"""

    database.execute("SET FOREIGN_KEY_CHECKS=0;")
    try:
        for table, table_comment in MYSQL_TABLE_COMMENTS.items():
            quoted_table = _quote_mysql_identifier(table)
            escaped_table_comment = _escape_mysql_comment(table_comment)
            database.execute(f"ALTER TABLE {quoted_table} COMMENT = '{escaped_table_comment}';")
            for column, column_comment in MYSQL_COLUMN_COMMENTS[table].items():
                quoted_column = _quote_mysql_identifier(column)
                escaped_column_comment = _escape_mysql_comment(column_comment.comment)
                statement = (
                    f"ALTER TABLE {quoted_table} MODIFY COLUMN {quoted_column} "
                    f"{column_comment.definition} COMMENT '{escaped_column_comment}';"
                )
                database.execute(statement)
    finally:
        database.execute("SET FOREIGN_KEY_CHECKS=1;")


def _quote_mysql_identifier(identifier: str) -> str:
    """转义 MySQL 标识符，避免 user/rank 等名称产生歧义。"""

    escaped = identifier.replace("`", "``")
    return f"`{escaped}`"


def _escape_mysql_comment(comment: str) -> str:
    """转义 MySQL COMMENT 字符串，确保中文注释可安全写入。"""

    return comment.replace("\\", "\\\\").replace("'", "''")


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
    Migration(5, "add_mysql_schema_comments", _migration_5_add_mysql_schema_comments),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
MYSQL_COMMENT_BASE_SCHEMA_VERSION = 4
MYSQL_COMMENT_SCHEMA_VERSION = 5

MYSQL_TABLE_COMMENTS: dict[str, str] = {
    "schema_migration": "数据库结构迁移历史表，记录已应用的 schema 版本。",
    "knowledge_base": "知识库主表，保存 RAG 问答可选择的数据集合。",
    "document": "文档主表，保存上传文件及其入库状态。",
    "ingest_job": "入库任务表，跟踪文档解析、切分、向量化和写入进度。",
    "conversation": "问答会话表，保存用户与知识库之间的会话元数据。",
    "message": "会话消息表，保存用户问题、助手回答和拒答信息。",
    "citation": "回答引用表，保存助手消息使用的证据片段。",
    "feedback": "用户反馈表，保存对助手回答的评价与修正建议。",
    "eval_set": "评测集表，保存一组可复现实验问题。",
    "eval_item": "评测样本表，保存单条评测问题及标准证据。",
    "eval_run": "评测运行表，保存一次检索评测的配置和汇总指标。",
    "eval_result": "评测结果表，保存单条评测样本的命中情况。",
    "user": "用户账号表，保存登录身份和账号状态。",
    "role": "角色表，保存 RBAC 角色及权限集合。",
    "user_role": "用户角色关联表，保存用户与角色的多对多关系。",
    "kb_access": "知识库授权表，保存用户对知识库的访问级别。",
    "refresh_token": "刷新令牌表，保存登录续期令牌的哈希与撤销状态。",
    "chat_run": "问答运行表，跟踪一次 ask 或流式问答的执行状态。",
}

MYSQL_COLUMN_COMMENTS: dict[str, dict[str, MysqlColumnComment]] = {
    "schema_migration": {
        "version": MysqlColumnComment("INTEGER NOT NULL", "schema 版本号。"),
        "name": MysqlColumnComment("TEXT NOT NULL", "迁移步骤名称。"),
        "applied_at": MysqlColumnComment("TEXT NOT NULL", "迁移应用时间，使用 ISO 字符串。"),
    },
    "knowledge_base": {
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "知识库唯一标识。"),
        "name": MysqlColumnComment("VARCHAR(255) NOT NULL", "知识库名称，建议全局唯一。"),
        "description": MysqlColumnComment("LONGTEXT NULL", "知识库说明，用于前端展示和管理识别。"),
        "visibility": MysqlColumnComment("VARCHAR(32) NOT NULL", "可见范围，例如 public/internal/admin。"),
        "config_json": MysqlColumnComment("LONGTEXT NOT NULL", "知识库检索与生成配置 JSON。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
        "deleted": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "软删除标记，1 表示已删除。"),
    },
    "document": {
        "doc_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "文档唯一标识。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "所属知识库 ID。"),
        "doc_name": MysqlColumnComment("VARCHAR(255) NOT NULL", "文档展示名称。"),
        "doc_version": MysqlColumnComment("VARCHAR(128) NULL", "文档版本号或人工维护版本。"),
        "published_at": MysqlColumnComment("VARCHAR(64) NULL", "文档发布日期，用于时效性判断。"),
        "source_uri": MysqlColumnComment("VARCHAR(1024) NULL", "原始来源链接，用于引用核验。"),
        "status": MysqlColumnComment("VARCHAR(32) NOT NULL", "文档入库状态。"),
        "error_message": MysqlColumnComment("LONGTEXT NULL", "入库失败时的可读错误信息。"),
        "chunk_count": MysqlColumnComment("INT NOT NULL DEFAULT 0", "已生成并写入的切片数量。"),
        "file_path": MysqlColumnComment("VARCHAR(1024) NULL", "本地存储路径或对象存储 key。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
        "deleted": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "软删除标记，1 表示已删除。"),
    },
    "ingest_job": {
        "job_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "入库任务唯一标识。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "任务所属知识库 ID。"),
        "doc_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "任务处理的文档 ID。"),
        "status": MysqlColumnComment("VARCHAR(32) NOT NULL", "任务状态。"),
        "progress_json": MysqlColumnComment("LONGTEXT NULL", "阶段进度、耗时和计数统计 JSON。"),
        "error_message": MysqlColumnComment("LONGTEXT NULL", "任务失败时的可读错误信息。"),
        "error_code": MysqlColumnComment("VARCHAR(64) NULL", "任务失败时的机器可读错误码。"),
        "started_at": MysqlColumnComment("VARCHAR(64) NULL", "任务开始时间，使用 ISO 字符串。"),
        "finished_at": MysqlColumnComment("VARCHAR(64) NULL", "任务结束时间，使用 ISO 字符串。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
    },
    "conversation": {
        "conversation_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "会话唯一标识。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "会话绑定的知识库 ID。"),
        "user_id": MysqlColumnComment("VARCHAR(128) NULL", "会话归属用户 ID，匿名或历史数据可为空。"),
        "title": MysqlColumnComment("VARCHAR(255) NULL", "会话标题。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
        "deleted": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "软删除标记，1 表示已删除。"),
    },
    "message": {
        "message_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "消息唯一标识。"),
        "conversation_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "所属会话 ID。"),
        "role": MysqlColumnComment("VARCHAR(32) NOT NULL", "消息角色，取值 user 或 assistant。"),
        "content": MysqlColumnComment("LONGTEXT NOT NULL", "消息正文。"),
        "refusal": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "是否为拒答消息。"),
        "refusal_reason": MysqlColumnComment("VARCHAR(64) NULL", "拒答原因码或简短原因。"),
        "timing_json": MysqlColumnComment("LONGTEXT NULL", "检索、生成、总耗时等计时 JSON。"),
        "suggestions_json": MysqlColumnComment("LONGTEXT NULL", "历史兼容的建议 JSON。"),
        "next_steps_json": MysqlColumnComment("LONGTEXT NULL", "拒答或澄清时的下一步建议 JSON。"),
        "citations_json": MysqlColumnComment("LONGTEXT NULL", "历史兼容的引用快照 JSON。"),
        "parent_message_id": MysqlColumnComment("VARCHAR(128) NULL", "分支消息的父消息 ID。"),
        "edited_from_message_id": MysqlColumnComment("VARCHAR(128) NULL", "编辑后重发来源消息 ID。"),
        "sequence_no": MysqlColumnComment("INT NULL", "会话内消息顺序号。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "request_id": MysqlColumnComment("VARCHAR(128) NULL", "本次请求 ID，用于日志追踪。"),
    },
    "citation": {
        "citation_row_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "引用记录唯一标识。"),
        "message_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "关联的助手消息 ID。"),
        "citation_id": MysqlColumnComment("INT NOT NULL", "回答中的引用编号，对应 [1][2]。"),
        "doc_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "证据所属文档 ID。"),
        "doc_name": MysqlColumnComment("VARCHAR(255) NOT NULL", "证据所属文档名称。"),
        "doc_version": MysqlColumnComment("VARCHAR(128) NULL", "证据所属文档版本。"),
        "published_at": MysqlColumnComment("VARCHAR(64) NULL", "证据文档发布日期。"),
        "page_start": MysqlColumnComment("INT NULL", "证据起始页码。"),
        "page_end": MysqlColumnComment("INT NULL", "证据结束页码。"),
        "section_path": MysqlColumnComment("VARCHAR(1024) NULL", "证据章节路径。"),
        "chunk_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "向量库切片 ID。"),
        "snippet": MysqlColumnComment("LONGTEXT NOT NULL", "引用片段摘要。"),
        "score": MysqlColumnComment("DOUBLE NULL", "检索相似度或重排得分。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "feedback": {
        "feedback_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "反馈唯一标识。"),
        "message_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "被反馈的助手消息 ID。"),
        "rating": MysqlColumnComment("VARCHAR(32) NOT NULL", "反馈评分，取值 up 或 down。"),
        "reasons_json": MysqlColumnComment("LONGTEXT NULL", "反馈原因列表 JSON。"),
        "comment": MysqlColumnComment("LONGTEXT NULL", "用户补充说明。"),
        "expected_hint": MysqlColumnComment("LONGTEXT NULL", "用户期望答案或修正提示。"),
        "status": MysqlColumnComment("VARCHAR(32) NOT NULL", "反馈处理状态。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "eval_set": {
        "eval_set_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "评测集唯一标识。"),
        "name": MysqlColumnComment("VARCHAR(255) NOT NULL", "评测集名称。"),
        "description": MysqlColumnComment("LONGTEXT NULL", "评测集说明。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "eval_item": {
        "eval_item_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "评测样本唯一标识。"),
        "eval_set_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "所属评测集 ID。"),
        "question": MysqlColumnComment("LONGTEXT NOT NULL", "评测问题。"),
        "gold_doc_id": MysqlColumnComment("VARCHAR(128) NULL", "标准命中文档 ID。"),
        "gold_page_start": MysqlColumnComment("INT NULL", "标准证据起始页码。"),
        "gold_page_end": MysqlColumnComment("INT NULL", "标准证据结束页码。"),
        "tags_json": MysqlColumnComment("LONGTEXT NULL", "样本标签 JSON。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "eval_run": {
        "run_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "评测运行唯一标识。"),
        "eval_set_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "本次运行使用的评测集 ID。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "本次运行评测的知识库 ID。"),
        "topk": MysqlColumnComment("INT NOT NULL", "检索返回的候选数量。"),
        "threshold": MysqlColumnComment("DOUBLE NULL", "额外分数阈值，空表示不启用。"),
        "rerank_enabled": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "是否启用重排。"),
        "metrics_json": MysqlColumnComment("LONGTEXT NULL", "Recall、MRR、延迟等汇总指标 JSON。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "eval_result": {
        "run_result_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "评测结果唯一标识。"),
        "run_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "所属评测运行 ID。"),
        "eval_item_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "对应评测样本 ID。"),
        "hit": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "标准证据是否命中 TopK。"),
        "rank": MysqlColumnComment("INT NULL", "标准证据在结果中的排名。"),
        "retrieve_ms": MysqlColumnComment("INT NULL", "单题检索耗时，单位毫秒。"),
        "notes": MysqlColumnComment("LONGTEXT NULL", "评测备注或诊断信息。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "user": {
        "user_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "用户唯一标识。"),
        "email": MysqlColumnComment("VARCHAR(255) NOT NULL", "登录邮箱。"),
        "password_hash": MysqlColumnComment("VARCHAR(255) NOT NULL", "密码哈希，不保存明文密码。"),
        "status": MysqlColumnComment("VARCHAR(32) NOT NULL", "账号状态。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
        "last_login_at": MysqlColumnComment("VARCHAR(64) NULL", "最近登录时间，使用 ISO 字符串。"),
    },
    "role": {
        "role_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "角色唯一标识。"),
        "name": MysqlColumnComment("VARCHAR(64) NOT NULL", "角色名称。"),
        "permissions_json": MysqlColumnComment("LONGTEXT NOT NULL", "权限标识列表 JSON。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "user_role": {
        "user_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "用户 ID。"),
        "role_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "角色 ID。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
    },
    "kb_access": {
        "user_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "被授权用户 ID。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "授权范围内的知识库 ID。"),
        "access_level": MysqlColumnComment("VARCHAR(32) NOT NULL", "访问级别，取值 read/write/admin。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "updated_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "最近更新时间，使用 ISO 字符串。"),
    },
    "refresh_token": {
        "token_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "刷新令牌唯一标识。"),
        "user_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "令牌所属用户 ID。"),
        "token_hash": MysqlColumnComment("VARCHAR(255) NOT NULL", "刷新令牌哈希值。"),
        "expires_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "令牌过期时间，使用 ISO 字符串。"),
        "revoked": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "是否已撤销。"),
        "created_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "创建时间，使用 ISO 字符串。"),
        "revoked_at": MysqlColumnComment("VARCHAR(64) NULL", "撤销时间，使用 ISO 字符串。"),
    },
    "chat_run": {
        "run_id": MysqlColumnComment("VARCHAR(128) NOT NULL", "问答运行唯一标识。"),
        "kb_id": MysqlColumnComment("VARCHAR(128) NULL", "运行使用的知识库 ID。"),
        "user_id": MysqlColumnComment("VARCHAR(128) NULL", "发起运行的用户 ID。"),
        "conversation_id": MysqlColumnComment("VARCHAR(128) NULL", "关联会话 ID。"),
        "user_message_id": MysqlColumnComment("VARCHAR(128) NULL", "本次运行产生或使用的用户消息 ID。"),
        "assistant_message_id": MysqlColumnComment("VARCHAR(128) NULL", "本次运行产生的助手消息 ID。"),
        "status": MysqlColumnComment("VARCHAR(32) NOT NULL", "运行状态。"),
        "cancel_flag": MysqlColumnComment("TINYINT(1) NOT NULL DEFAULT 0", "取消标记，1 表示用户请求取消。"),
        "started_at": MysqlColumnComment("VARCHAR(64) NOT NULL", "运行开始时间，使用 ISO 字符串。"),
        "finished_at": MysqlColumnComment("VARCHAR(64) NULL", "运行结束时间，使用 ISO 字符串。"),
        "request_id": MysqlColumnComment("VARCHAR(128) NULL", "本次请求 ID，用于日志追踪。"),
    },
}

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
        suggestions_json LONGTEXT NULL,
        next_steps_json LONGTEXT NULL,
        citations_json LONGTEXT NULL,
        parent_message_id VARCHAR(128) NULL,
        edited_from_message_id VARCHAR(128) NULL,
        sequence_no INT NULL,
        created_at VARCHAR(64) NOT NULL,
        request_id VARCHAR(128) NULL,
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
