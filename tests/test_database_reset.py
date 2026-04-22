from __future__ import annotations

from app.core.settings import Settings
from app.db import database as database_module


class FakeResetDatabase:
    """用于验证测试库清空顺序的最小假数据库。"""

    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append(" ".join(statement.split()))


def test_reset_database_deletes_chat_run_before_user_dependencies(
    monkeypatch,
) -> None:
    """chat_run 必须先于其依赖的父表删除，避免 MySQL 外键重置失败。"""

    fake_database = FakeResetDatabase()

    monkeypatch.setattr(database_module, "get_database", lambda settings: fake_database)
    monkeypatch.setattr(database_module, "_init_schema", lambda database: None)
    monkeypatch.setattr(database_module, "_seed_default_roles", lambda database: None)

    database_module.reset_database(
        Settings(database_url="sqlite:///./data/test-reset.db", jwt_secret_key="test-secret")
    )

    assert fake_database.executed.index("DELETE FROM chat_run;") < fake_database.executed.index(
        "DELETE FROM user;"
    )
    assert fake_database.executed.index("DELETE FROM chat_run;") < fake_database.executed.index(
        "DELETE FROM message;"
    )
    assert fake_database.executed.index("DELETE FROM chat_run;") < fake_database.executed.index(
        "DELETE FROM conversation;"
    )
