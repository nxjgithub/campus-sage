"""每周回归脚本：串联 API smoke 与离线 eval，并输出统一报告。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    """脚本入口。"""

    parser = argparse.ArgumentParser(description="运行每周联调回归（smoke + eval）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="后端服务地址")
    parser.add_argument("--admin-email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument("--admin-password", default="Admin1234", help="管理员密码")
    parser.add_argument(
        "--create-admin-if-missing",
        action="store_true",
        help="当管理员不存在时自动创建",
    )
    parser.add_argument("--kb-id", default=None, help="eval 使用的知识库 ID")
    parser.add_argument("--eval-file", default=None, help="eval 数据集 JSON 路径")
    parser.add_argument("--topk", type=int, default=5, help="eval TopK")
    parser.add_argument("--threshold", type=float, default=None, help="eval 阈值")
    parser.add_argument("--rerank-enabled", action="store_true", help="eval 是否启用重排")
    parser.add_argument(
        "--output",
        default=None,
        help="回归报告输出路径，默认 data/weekly_regression_<run_id>.json",
    )
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:8]
    start_time = time.time()
    python_bin = sys.executable
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    smoke_report_path = data_dir / f"api_smoke_{run_id}.json"
    smoke_result = _run_smoke(
        python_bin=python_bin,
        base_url=args.base_url,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        create_admin_if_missing=args.create_admin_if_missing,
        output_path=smoke_report_path,
    )
    eval_result = _run_eval(
        python_bin=python_bin,
        kb_id=args.kb_id,
        eval_file=args.eval_file,
        topk=args.topk,
        threshold=args.threshold,
        rerank_enabled=args.rerank_enabled,
    )

    end_time = time.time()
    report = {
        "run_id": run_id,
        "started_at": _utc_now_iso(start_time),
        "finished_at": _utc_now_iso(end_time),
        "duration_ms": int((end_time - start_time) * 1000),
        "base_url": args.base_url,
        "smoke": smoke_result,
        "eval": eval_result,
        "summary": {
            "smoke_ok": bool(smoke_result.get("ok")),
            "eval_ok": bool(eval_result.get("ok")),
            "overall_ok": bool(smoke_result.get("ok")) and bool(eval_result.get("ok")),
        },
    }

    output_path = Path(args.output) if args.output else data_dir / f"weekly_regression_{run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "report_path": str(output_path),
            },
            ensure_ascii=True,
        )
    )
    if not report["summary"]["overall_ok"]:
        raise SystemExit(1)


def _run_smoke(
    *,
    python_bin: str,
    base_url: str,
    admin_email: str,
    admin_password: str,
    create_admin_if_missing: bool,
    output_path: Path,
) -> dict[str, object]:
    """执行 smoke 脚本并解析结果。"""

    command = [
        python_bin,
        "scripts/run_api_smoke.py",
        "--base-url",
        base_url,
        "--admin-email",
        admin_email,
        "--admin-password",
        admin_password,
        "--output",
        str(output_path),
    ]
    if create_admin_if_missing:
        command.append("--create-admin-if-missing")

    started = time.time()
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed_ms = int((time.time() - started) * 1000)
    payload: dict[str, object] | None = None
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None

    summary = payload.get("summary") if isinstance(payload, dict) else {}
    failed_count = int((summary or {}).get("failed") or 0)
    ok = completed.returncode == 0 and failed_count == 0
    return {
        "ok": ok,
        "duration_ms": elapsed_ms,
        "command": command,
        "report_path": str(output_path) if output_path.exists() else None,
        "summary": summary or None,
        "stderr_tail": _tail(completed.stderr),
    }


def _run_eval(
    *,
    python_bin: str,
    kb_id: str | None,
    eval_file: str | None,
    topk: int,
    threshold: float | None,
    rerank_enabled: bool,
) -> dict[str, object]:
    """执行 eval 脚本并解析结果。"""

    if not kb_id or not eval_file:
        return {
            "ok": True,
            "executed": False,
            "reason": "missing_kb_id_or_eval_file",
        }

    command = [
        python_bin,
        "scripts/run_eval.py",
        "--kb-id",
        kb_id,
        "--eval-file",
        eval_file,
        "--topk",
        str(topk),
    ]
    if threshold is not None:
        command.extend(["--threshold", str(threshold)])
    if rerank_enabled:
        command.append("--rerank-enabled")

    started = time.time()
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed_ms = int((time.time() - started) * 1000)
    parsed_output: dict[str, object] | None = None
    if completed.stdout.strip():
        try:
            parsed_output = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed_output = None

    return {
        "ok": completed.returncode == 0,
        "executed": True,
        "duration_ms": elapsed_ms,
        "command": command,
        "result": parsed_output,
        "stderr_tail": _tail(completed.stderr),
    }


def _tail(text: str, limit: int = 400) -> str | None:
    """截断过长 stderr，避免报告膨胀。"""

    cleaned = text.strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _utc_now_iso(timestamp: float) -> str:
    """将时间戳转为 UTC ISO 字符串。"""

    return datetime.fromtimestamp(timestamp, tz=UTC).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
