from types import SimpleNamespace

from app.core.error_codes import ErrorCode
from app.ingest import queue_hooks


class FakeDocumentService:
    def __init__(self) -> None:
        self.failed_payload: dict[str, object] | None = None

    def mark_job_failed(
        self,
        doc_id: str,
        job_id: str,
        error_message: str,
        error_code: str,
    ) -> None:
        self.failed_payload = {
            "doc_id": doc_id,
            "job_id": job_id,
            "error_message": error_message,
            "error_code": error_code,
        }


def test_on_ingest_failure_accepts_rq_connection_argument(monkeypatch) -> None:
    service = FakeDocumentService()
    job = SimpleNamespace(
        args=("doc_1", "job_1", "req_1"),
        origin="ingest",
        retries_left=1,
    )
    monkeypatch.setattr(queue_hooks, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(queue_hooks, "build_document_service", lambda settings: service)
    monkeypatch.setattr(queue_hooks, "_move_to_dead", lambda failed_job, settings: None)
    monkeypatch.setattr(queue_hooks, "_trim_dead_if_needed", lambda settings: None)

    queue_hooks.on_ingest_failure(
        job,
        SimpleNamespace(),
        RuntimeError,
        RuntimeError("失败"),
        None,
    )

    assert service.failed_payload == {
        "doc_id": "doc_1",
        "job_id": "job_1",
        "error_message": "RuntimeError: 失败",
        "error_code": ErrorCode.INGEST_WORKER_FAILED.value,
    }


def test_on_ingest_failure_swallows_callback_errors(monkeypatch) -> None:
    job = SimpleNamespace(
        id="rq_1",
        args=("doc_1", "job_1", "req_1"),
        origin="ingest",
        retries_left=1,
    )
    monkeypatch.setattr(queue_hooks, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        queue_hooks,
        "build_document_service",
        lambda settings: (_ for _ in ()).throw(RuntimeError("数据库暂不可用")),
    )

    queue_hooks.on_ingest_failure(
        job,
        SimpleNamespace(),
        RuntimeError,
        RuntimeError("失败"),
        None,
    )
