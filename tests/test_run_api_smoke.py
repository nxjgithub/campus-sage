from __future__ import annotations

from scripts.run_api_smoke import SmokeRunner


def test_wait_job_logs_status_change_and_returns_terminal_state(
    monkeypatch, capsys
) -> None:
    """入库轮询应在状态变化时输出进度，并在结束态返回结果。"""

    runner = SmokeRunner(
        base_url="http://test.local",
        admin_email="admin@example.com",
        admin_password="Admin1234",
        timeout_seconds=5,
        create_admin_if_missing=False,
        poll_interval_seconds=0.2,
        ingest_timeout_seconds=10,
    )
    responses = iter(
        [
            (
                object(),
                {
                    "status": "queued",
                    "progress": {
                        "stage": "parse",
                    },
                },
            ),
            (
                object(),
                {
                    "status": "succeeded",
                    "progress": {
                        "stage": "done",
                    },
                },
            ),
        ]
    )

    monkeypatch.setattr(runner, "_request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("scripts.run_api_smoke.time.sleep", lambda *_args, **_kwargs: None)

    result = runner._wait_job("job_demo", timeout_seconds=5)

    assert result["status"] == "succeeded"
    captured = capsys.readouterr().out
    assert "入库任务状态更新" in captured
    assert "status=queued" in captured
    assert "status=succeeded" in captured


def test_wait_job_logs_transient_request_failures_and_recovers(
    monkeypatch, capsys
) -> None:
    """轮询遇到瞬时断连时应输出提示，并在后续恢复后继续完成。"""

    runner = SmokeRunner(
        base_url="http://test.local",
        admin_email="admin@example.com",
        admin_password="Admin1234",
        timeout_seconds=5,
        create_admin_if_missing=False,
        poll_interval_seconds=0.2,
        ingest_timeout_seconds=10,
    )
    responses = iter(
        [
            (None, {}),
            (
                object(),
                {
                    "status": "succeeded",
                    "progress": {
                        "stage": "done",
                    },
                },
            ),
        ]
    )

    monkeypatch.setattr(runner, "_request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("scripts.run_api_smoke.time.sleep", lambda *_args, **_kwargs: None)

    result = runner._wait_job("job_demo", timeout_seconds=5)

    assert result["status"] == "succeeded"
    captured = capsys.readouterr().out
    assert "轮询入库任务异常" in captured
    assert "failures=1" in captured
