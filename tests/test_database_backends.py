from __future__ import annotations

import pytest

from app.core.settings import Settings
from app.db.database import _convert_qmark_placeholders, _parse_database_config
from app.db.migrations import LATEST_SCHEMA_VERSION, run_mysql_migrations


class FakeMigrationDatabase:
    """用于验证 MySQL schema 初始化流程的最小假数据库。"""

    def __init__(self, current_version: int = 0) -> None:
        self.current_version = current_version
        self.executed: list[str] = []

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        normalized = " ".join(statement.split())
        self.executed.append(normalized)
        if "INSERT INTO schema_migration" in normalized:
            self.current_version = max(self.current_version, int(params[0]))

    def fetch_one(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> dict[str, object] | None:
        normalized = " ".join(statement.split())
        if "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migration;" in normalized:
            return {"version": self.current_version}
        return None

    def fetch_all(
        self, statement: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        return []


def test_parse_mysql_database_config() -> None:
    """MySQL 连接串应被解析为统一数据库配置。"""

    config = _parse_database_config(
        "mysql+pymysql://csage:secret@127.0.0.1:3307/csage_demo?charset=utf8mb4"
    )

    assert config.backend == "mysql"
    assert config.host == "127.0.0.1"
    assert config.port == 3307
    assert config.username == "csage"
    assert config.password == "secret"
    assert config.database_name == "csage_demo"
    assert config.charset == "utf8mb4"


def test_convert_qmark_placeholders_for_mysql() -> None:
    """问号占位符应在 MySQL 模式下转换为 `%s`。"""

    statement = """
    SELECT user_id, email
    FROM user
    WHERE status = ? AND (email LIKE ? OR user_id LIKE ?)
    LIMIT ? OFFSET ?;
    """

    converted = _convert_qmark_placeholders(statement)

    assert converted.count("%s") == 5
    assert "status = %s" in converted
    assert "LIMIT %s OFFSET %s" in converted


def test_run_mysql_migrations_bootstraps_latest_schema() -> None:
    """空 MySQL 数据库应被初始化到当前最新版本。"""

    database = FakeMigrationDatabase()

    run_mysql_migrations(database)

    assert database.current_version == LATEST_SCHEMA_VERSION
    assert any("CREATE TABLE IF NOT EXISTS knowledge_base" in item for item in database.executed)
    assert any("CREATE TABLE IF NOT EXISTS chat_run" in item for item in database.executed)
    assert any("ALTER TABLE `knowledge_base` COMMENT" in item for item in database.executed)
    assert any(
        "MODIFY COLUMN `kb_id` VARCHAR(128) NOT NULL COMMENT" in item
        for item in database.executed
    )


def test_run_mysql_migrations_upgrades_v4_comments() -> None:
    """已初始化到 v4 的 MySQL 库应允许补齐中文注释元数据。"""

    database = FakeMigrationDatabase(current_version=4)

    run_mysql_migrations(database)

    assert database.current_version == LATEST_SCHEMA_VERSION
    assert any("ALTER TABLE `document` COMMENT" in item for item in database.executed)
    assert any(
        "MODIFY COLUMN `doc_name` VARCHAR(255) NOT NULL COMMENT" in item
        for item in database.executed
    )


def test_run_mysql_migrations_rejects_partial_legacy_version() -> None:
    """MySQL 旧版本库当前不允许做增量升级。"""

    database = FakeMigrationDatabase(current_version=1)

    with pytest.raises(RuntimeError, match="仅支持空库初始化"):
        run_mysql_migrations(database)


def test_settings_database_target_masks_mysql_credentials() -> None:
    """运行时诊断中的 MySQL 目标描述不应暴露账号口令。"""

    settings = Settings(
        database_url="mysql+pymysql://csage:secret@mysql.internal:3306/csage?charset=utf8mb4"
    )

    assert settings.database_backend == "mysql"
    assert settings.database_target == "mysql.internal:3306/csage"
