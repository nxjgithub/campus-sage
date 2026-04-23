from __future__ import annotations
# ruff: noqa: E402

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth.service import UserService
from app.core.settings import get_settings
from app.db.database import get_database, init_database
from app.db.repos import RepositoryProvider


def main() -> None:
    """创建管理员账号。"""

    parser = argparse.ArgumentParser(description="创建管理员账号")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument("--password", required=True, help="管理员密码")
    args = parser.parse_args()

    settings = get_settings()
    init_database(settings)
    provider = RepositoryProvider(get_database(settings))
    service = UserService(
        provider.user(),
        provider.role(),
        provider.kb_access(),
        settings,
    )
    service.ensure_roles_seeded()
    service.create_user(args.email, args.password, ["admin"])
    print("管理员账号创建成功")


if __name__ == "__main__":
    main()
