from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


def test_create_admin_script_can_run_from_repo_root(tmp_path: Path) -> None:
    """直接执行脚本时也应能从仓库根目录导入项目包。"""

    database_path = tmp_path / "create_admin_script.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["VECTOR_BACKEND"] = "memory"
    env["EMBEDDING_BACKEND"] = "simple"
    env["INGEST_QUEUE_ENABLED"] = "false"
    env["VLLM_ENABLED"] = "false"
    env["JWT_SECRET_KEY"] = "test-secret-key-with-32-bytes-minimum!!"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_admin.py",
            "--email",
            "admin_script@example.com",
            "--password",
            "Admin1234",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "管理员账号创建成功" in result.stdout
    assert database_path.exists()
