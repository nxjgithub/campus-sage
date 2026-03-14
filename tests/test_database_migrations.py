from __future__ import annotations

from pathlib import Path

from app.auth.permissions import DEFAULT_ROLE_PERMISSIONS
from app.core.settings import Settings
from app.db.database import (
    Database,
    DatabaseConfig,
    get_database,
    init_database,
    reset_database_singleton,
)
from app.db.migrations import LATEST_SCHEMA_VERSION, get_current_schema_version, run_sqlite_migrations


def test_run_sqlite_migrations_initializes_empty_database(tmp_path: Path) -> None:
    database = Database(DatabaseConfig(path=tmp_path / "fresh.db"))

    try:
        run_sqlite_migrations(database)

        assert get_current_schema_version(database) == LATEST_SCHEMA_VERSION
        assert _table_exists(database, "schema_migration")
        assert _table_exists(database, "chat_run")
        assert _column_names(database, "document") >= {"doc_id", "source_uri"}
        assert _column_names(database, "message") >= {
            "message_id",
            "next_steps_json",
            "parent_message_id",
            "edited_from_message_id",
            "sequence_no",
        }
    finally:
        database.close()


def test_run_sqlite_migrations_upgrades_legacy_database(tmp_path: Path) -> None:
    database = Database(DatabaseConfig(path=tmp_path / "legacy.db"))

    try:
        _create_legacy_schema(database)

        run_sqlite_migrations(database)
        run_sqlite_migrations(database)

        assert get_current_schema_version(database) == LATEST_SCHEMA_VERSION
        assert _column_names(database, "document") >= {"doc_id", "source_uri"}
        assert _column_names(database, "ingest_job") >= {
            "job_id",
            "error_code",
            "started_at",
            "finished_at",
        }
        assert _column_names(database, "conversation") >= {"conversation_id", "user_id"}
        assert _column_names(database, "message") >= {
            "message_id",
            "next_steps_json",
            "parent_message_id",
            "edited_from_message_id",
            "sequence_no",
        }
        assert _table_exists(database, "role")
        assert _table_exists(database, "refresh_token")
        assert _table_exists(database, "chat_run")
        assert _migration_versions(database) == list(range(1, LATEST_SCHEMA_VERSION + 1))
    finally:
        database.close()


def test_init_database_seeds_default_roles(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
        jwt_secret_key="test-secret",
    )
    reset_database_singleton()

    try:
        init_database(settings)
        database = get_database(settings)
        rows = database.fetch_all("SELECT name FROM role ORDER BY name;")
        assert [row["name"] for row in rows] == sorted(DEFAULT_ROLE_PERMISSIONS)
    finally:
        reset_database_singleton()


def _create_legacy_schema(database: Database) -> None:
    """构造未引入迁移表的旧版核心 schema。"""

    database.execute(
        """
        CREATE TABLE knowledge_base (
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
        CREATE TABLE document (
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
            deleted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    database.execute(
        """
        CREATE TABLE ingest_job (
            job_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_json TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    database.execute(
        """
        CREATE TABLE conversation (
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
        CREATE TABLE message (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            refusal INTEGER NOT NULL,
            refusal_reason TEXT,
            timing_json TEXT,
            citations_json TEXT,
            created_at TEXT NOT NULL
        );
        """
    )


def _column_names(database: Database, table: str) -> set[str]:
    return {str(row["name"]) for row in database.fetch_all(f"PRAGMA table_info({table});")}


def _migration_versions(database: Database) -> list[int]:
    rows = database.fetch_all("SELECT version FROM schema_migration ORDER BY version;")
    return [int(row["version"]) for row in rows]


def _table_exists(database: Database, table: str) -> bool:
    return (
        database.fetch_one(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?;
            """,
            (table,),
        )
        is not None
    )
