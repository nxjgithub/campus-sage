"""执行 API 联调 smoke，用于本地验收与 CI 门禁。"""

from __future__ import annotations
# ruff: noqa: E402, PLR0915

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth.service import UserService
from app.core.settings import get_settings
from app.db.database import get_database
from app.db.repos import RepositoryProvider


@dataclass(slots=True)
class SmokeCaseResult:
    """记录单条 smoke 检查结果。"""

    name: str
    ok: bool
    status: int | None
    detail: str


class SmokeRunner:
    """封装 smoke 执行流程，便于复用与扩展。"""

    def __init__(
        self,
        *,
        base_url: str,
        admin_email: str,
        admin_password: str,
        timeout_seconds: int,
        create_admin_if_missing: bool,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.timeout_seconds = timeout_seconds
        self.create_admin_if_missing = create_admin_if_missing
        self.run_id = uuid.uuid4().hex[:8]
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=float(timeout_seconds),
            trust_env=False,
        )
        self.results: list[SmokeCaseResult] = []
        self.state: dict[str, str | None] = {
            "access_token": None,
            "refresh_token": None,
            "kb_id": None,
            "doc_id": None,
            "job_id": None,
            "conversation_id": None,
            "message_id": None,
            "eval_set_id": None,
            "eval_run_id": None,
            "temp_file": None,
        }

    def run(self) -> dict[str, object]:
        """执行完整 smoke 流程并返回报告。"""

        q_clarify = "\u8fd9\u4e2a\u600e\u4e48\u529e"
        q_followup = "\u8865\u8003\u7533\u8bf7\u6761\u4ef6\u662f\u4ec0\u4e48\uff1f"
        q_latest = "\u6700\u65b0\u8865\u8003\u7533\u8bf7\u6761\u4ef6\u662f\u4ec0\u4e48\uff1f"
        doc_text = (
            "# \u8865\u8003\u89c4\u5b9a\n\n"
            "\u8865\u8003\u7533\u8bf7\u6761\u4ef6\uff1a"
            "\u672c\u79d1\u751f\u5728\u89c4\u5b9a\u65f6\u95f4\u5185\u63d0\u4ea4\u7533\u8bf7\uff0c"
            "\u7ecf\u5b66\u9662\u5ba1\u6838\u540e\u53ef\u53c2\u52a0\u8865\u8003\u3002\n"
        )
        try:
            self._request(
                "auth.required.kb_list",
                "GET",
                "/api/v1/kb",
                expected={401, 403},
            )

            response_body = self._login()
            if response_body is None:
                raise RuntimeError("\u767b\u5f55\u5931\u8d25")

            self._request(
                "auth.refresh",
                "POST",
                "/api/v1/auth/refresh",
                expected={200},
                json={"refresh_token": self.state["refresh_token"]},
            )
            self._request("users.me", "GET", "/api/v1/users/me", token=True, expected={200})
            self._request("roles.list", "GET", "/api/v1/roles", token=True, expected={200})
            _, runtime_payload = self._request(
                "monitor.runtime",
                "GET",
                "/api/v1/monitor/runtime",
                token=True,
                expected={200},
            )
            if isinstance(runtime_payload, dict):
                rag_metrics = runtime_payload.get("rag_metrics")
                runtime_ok = isinstance(rag_metrics, dict) and all(
                    key in rag_metrics
                    for key in (
                        "sample_size",
                        "refusal_rate",
                        "clarification_rate",
                        "freshness_warning_rate",
                        "citation_coverage_rate",
                    )
                )
                self._record(
                    "monitor.runtime.contract",
                    runtime_ok,
                    200,
                    self._short_json(rag_metrics),
                )
            self._request("monitor.queues", "GET", "/api/v1/monitor/queues", token=True, expected={200})

            _, kb_payload = self._request(
                "kb.create",
                "POST",
                "/api/v1/kb",
                token=True,
                expected={200},
                json={
                    "name": f"smoke-kb-{self.run_id}",
                    "description": "api smoke",
                    "visibility": "internal",
                    "config": {
                        "topk": 1,
                        "threshold": 0.0,
                        "rerank_enabled": False,
                        "max_context_tokens": 3000,
                        "min_evidence_chunks": 1,
                        "min_context_chars": 1,
                        "min_keyword_coverage": 0.0,
                    },
                },
            )
            if isinstance(kb_payload, dict):
                self.state["kb_id"] = kb_payload.get("kb_id")

            self._request("kb.list", "GET", "/api/v1/kb", token=True, expected={200})
            self._request("kb.detail", "GET", f"/api/v1/kb/{self.state['kb_id']}", token=True, expected={200})
            self._request(
                "kb.invalid_patch",
                "PATCH",
                f"/api/v1/kb/{self.state['kb_id']}",
                token=True,
                expected={400, 422},
                json={"config": {"topk": 0}},
            )

            temp_path = Path("data") / f"api_smoke_{self.run_id}.md"
            temp_path.write_text(doc_text, encoding="utf-8")
            self.state["temp_file"] = str(temp_path)
            with temp_path.open("rb") as file_obj:
                _, upload_payload = self._request(
                    "documents.upload",
                    "POST",
                    f"/api/v1/kb/{self.state['kb_id']}/documents",
                    token=True,
                    expected={200},
                    files={"file": (temp_path.name, file_obj, "text/markdown")},
                    data={
                        "doc_name": f"api_smoke_{self.run_id}.md",
                        "published_at": "2020-01-01",
                        "source_uri": "https://example.edu/academic/policy",
                    },
                )
            if isinstance(upload_payload, dict):
                self.state["doc_id"] = (upload_payload.get("doc") or {}).get("doc_id")
                self.state["job_id"] = (upload_payload.get("job") or {}).get("job_id")

            self._request(
                "documents.list",
                "GET",
                f"/api/v1/kb/{self.state['kb_id']}/documents",
                token=True,
                expected={200},
            )
            self._request(
                "documents.detail",
                "GET",
                f"/api/v1/documents/{self.state['doc_id']}",
                token=True,
                expected={200},
            )

            if self.state["job_id"]:
                job_result = self._wait_job(str(self.state["job_id"]), timeout_seconds=180)
                self._record(
                    "ingest.job.final",
                    job_result.get("status") == "succeeded",
                    200,
                    self._short_json(job_result),
                )

            _, clarify_payload = self._request(
                "rag.ask.clarification",
                "POST",
                f"/api/v1/kb/{self.state['kb_id']}/ask",
                token=True,
                expected={200},
                json={"question": q_clarify},
            )
            if isinstance(clarify_payload, dict):
                self.state["conversation_id"] = clarify_payload.get("conversation_id")
                self.state["message_id"] = clarify_payload.get("message_id")
                clarify_ok = (
                    clarify_payload.get("refusal") is True
                    and any(
                        item.get("action") in {"add_context", "rewrite_question"}
                        for item in (clarify_payload.get("next_steps") or [])
                    )
                )
                self._record(
                    "rag.ask.clarification.contract",
                    clarify_ok,
                    200,
                    self._short_json(clarify_payload),
                )

            _, followup_payload = self._request(
                "rag.ask.followup",
                "POST",
                f"/api/v1/kb/{self.state['kb_id']}/ask",
                token=True,
                expected={200},
                json={
                    "question": q_followup,
                    "conversation_id": self.state["conversation_id"],
                },
            )
            if isinstance(followup_payload, dict):
                self.state["message_id"] = followup_payload.get("message_id") or self.state["message_id"]
                followup_ok = (
                    followup_payload.get("conversation_id") == self.state["conversation_id"]
                    and followup_payload.get("refusal") is False
                )
                self._record(
                    "rag.ask.followup.contract",
                    followup_ok,
                    200,
                    self._short_json(followup_payload),
                )

            _, latest_payload = self._request(
                "rag.ask.latest_warning",
                "POST",
                f"/api/v1/kb/{self.state['kb_id']}/ask",
                token=True,
                expected={200},
                json={
                    "question": q_latest,
                    "conversation_id": self.state["conversation_id"],
                },
            )
            if isinstance(latest_payload, dict):
                latest_ok = (
                    latest_payload.get("refusal") is False
                    and "\u63d0\u793a\uff1a\u95ee\u9898\u6d89\u53ca\u65f6\u6548"
                    in str(latest_payload.get("answer"))
                    and any(
                        item.get("action") == "check_official_source"
                        for item in (latest_payload.get("next_steps") or [])
                    )
                )
                self._record(
                    "rag.ask.latest_warning.contract",
                    latest_ok,
                    200,
                    self._short_json(latest_payload),
                )

            if self.state["message_id"]:
                self._request(
                    "message.regenerate",
                    "POST",
                    f"/api/v1/messages/{self.state['message_id']}/regenerate",
                    token=True,
                    expected={200},
                    json={"topk": 1},
                )
                self._request(
                    "message.feedback",
                    "POST",
                    f"/api/v1/messages/{self.state['message_id']}/feedback",
                    token=True,
                    expected={200},
                    json={"rating": "up", "reasons": ["ACCURATE"], "comment": "smoke"},
                )

            self._request(
                "conversation.detail",
                "GET",
                f"/api/v1/conversations/{self.state['conversation_id']}",
                token=True,
                expected={200},
            )
            self._request(
                "conversation.messages.page",
                "GET",
                f"/api/v1/conversations/{self.state['conversation_id']}/messages",
                token=True,
                expected={200},
                params={"limit": 10},
            )

            _, eval_set_payload = self._request(
                "eval.set.create",
                "POST",
                "/api/v1/eval/sets",
                token=True,
                expected={200},
                json={
                    "name": f"smoke-eval-{self.run_id}",
                    "items": [
                        {
                            "question": q_followup,
                            "gold_doc_id": self.state["doc_id"],
                            "gold_page_start": 1,
                            "gold_page_end": 1,
                        }
                    ],
                },
            )
            if isinstance(eval_set_payload, dict):
                self.state["eval_set_id"] = eval_set_payload.get("eval_set_id")

            if self.state.get("eval_set_id"):
                _, eval_run_payload = self._request(
                    "eval.run.create",
                    "POST",
                    "/api/v1/eval/runs",
                    token=True,
                    expected={200},
                    json={
                        "eval_set_id": self.state["eval_set_id"],
                        "kb_id": self.state["kb_id"],
                        "topk": 1,
                    },
                )
                if isinstance(eval_run_payload, dict):
                    self.state["eval_run_id"] = eval_run_payload.get("run_id")

            if self.state.get("eval_run_id"):
                self._request(
                    "eval.run.get",
                    "GET",
                    f"/api/v1/eval/runs/{self.state['eval_run_id']}",
                    token=True,
                    expected={200},
                )

            self._request(
                "auth.logout",
                "POST",
                "/api/v1/auth/logout",
                token=True,
                expected={200},
                json={"refresh_token": self.state["refresh_token"]},
            )
        finally:
            self._cleanup()

        summary = {
            "base_url": self.base_url,
            "run_id": self.run_id,
            "total": len(self.results),
            "passed": sum(1 for item in self.results if item.ok),
        }
        summary["failed"] = summary["total"] - summary["passed"]
        failed_cases = [asdict(item) for item in self.results if not item.ok]
        return {
            "summary": summary,
            "failed_cases": failed_cases,
            "all_cases": [asdict(item) for item in self.results],
        }

    def _login(self) -> dict[str, object] | None:
        """登录管理员，必要时自动创建。"""

        _, payload = self._request(
            "auth.login",
            "POST",
            "/api/v1/auth/login",
            expected={200, 401},
            json={"email": self.admin_email, "password": self.admin_password},
        )
        if isinstance(payload, dict) and payload.get("access_token"):
            self.state["access_token"] = str(payload.get("access_token"))
            self.state["refresh_token"] = str(payload.get("refresh_token"))
            return payload
        if not self.create_admin_if_missing:
            return None
        self._ensure_admin_user()
        _, payload = self._request(
            "auth.login.retry",
            "POST",
            "/api/v1/auth/login",
            expected={200},
            json={"email": self.admin_email, "password": self.admin_password},
        )
        if isinstance(payload, dict):
            self.state["access_token"] = payload.get("access_token")
            self.state["refresh_token"] = payload.get("refresh_token")
            return payload
        return None

    def _ensure_admin_user(self) -> None:
        """在本地数据库中确保管理员账号存在。"""

        settings = get_settings()
        provider = RepositoryProvider(get_database(settings))
        if provider.user().get_by_email(self.admin_email) is not None:
            return
        service = UserService(
            provider.user(),
            provider.role(),
            provider.kb_access(),
            settings,
        )
        service.ensure_roles_seeded()
        service.create_user(self.admin_email, self.admin_password, ["admin"])

    def _wait_job(self, job_id: str, timeout_seconds: int) -> dict[str, object]:
        """轮询入库任务直到结束。"""

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            _, body = self._request(
                f"ingest.job.poll.{job_id}",
                "GET",
                f"/api/v1/ingest/jobs/{job_id}",
                token=True,
                expected={200},
            )
            if isinstance(body, dict) and body.get("status") in {"succeeded", "failed", "canceled"}:
                return body
            time.sleep(1)
        return {"status": "timeout"}

    def _request(
        self,
        name: str,
        method: str,
        path: str,
        *,
        token: bool = False,
        expected: set[int] | None = None,
        **kwargs,
    ) -> tuple[httpx.Response | None, object]:
        """发起请求并记录结果。"""

        headers = kwargs.pop("headers", {})
        if token and self.state["access_token"]:
            headers["Authorization"] = f"Bearer {self.state['access_token']}"
        try:
            response = self.client.request(method, path, headers=headers, **kwargs)
        except Exception as exc:
            self._record(name, False, None, f"request_failed={exc}")
            return None, {}
        try:
            payload: object = response.json()
        except Exception:
            payload = response.text
        ok = response.status_code in set(expected or {response.status_code})
        self._record(
            name,
            ok,
            response.status_code,
            f"request_id={response.headers.get('X-Request-ID')}, payload={self._short_json(payload)}",
        )
        return response, payload

    def _cleanup(self) -> None:
        """清理 smoke 临时资源，保证幂等。"""

        try:
            if self.state["doc_id"]:
                self._request(
                    "cleanup.doc",
                    "DELETE",
                    f"/api/v1/documents/{self.state['doc_id']}",
                    token=True,
                    expected={200, 404},
                )
            if self.state["conversation_id"]:
                self._request(
                    "cleanup.conversation",
                    "DELETE",
                    f"/api/v1/conversations/{self.state['conversation_id']}",
                    token=True,
                    expected={200, 404},
                )
            if self.state["kb_id"]:
                self._request(
                    "cleanup.kb",
                    "DELETE",
                    f"/api/v1/kb/{self.state['kb_id']}",
                    token=True,
                    expected={200, 404},
                )
        finally:
            if self.state["temp_file"]:
                temp_path = Path(str(self.state["temp_file"]))
                if temp_path.exists():
                    temp_path.unlink()
            self.client.close()

    def _record(self, name: str, ok: bool, status: int | None, detail: str) -> None:
        """写入单条检查结果。"""

        self.results.append(SmokeCaseResult(name=name, ok=ok, status=status, detail=detail))

    @staticmethod
    def _short_json(payload: object, limit: int = 280) -> str:
        """压缩输出体，避免日志过长。"""

        try:
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            text = str(payload)
        return text if len(text) <= limit else f"{text[:limit]}..."


def main() -> None:
    """脚本入口。"""

    parser = argparse.ArgumentParser(description="运行 CampusSage API smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="后端服务地址")
    parser.add_argument("--admin-email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument("--admin-password", default="Admin1234", help="管理员密码")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="单请求超时时间（秒）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="报告输出路径，默认写入 data/api_smoke_<run_id>.json",
    )
    parser.add_argument(
        "--create-admin-if-missing",
        action="store_true",
        help="登录失败时自动创建管理员",
    )
    args = parser.parse_args()

    runner = SmokeRunner(
        base_url=args.base_url,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        timeout_seconds=max(5, args.timeout_seconds),
        create_admin_if_missing=args.create_admin_if_missing,
    )
    report = runner.run()
    run_id = report["summary"]["run_id"]
    output_path = Path(args.output) if args.output else Path("data") / f"api_smoke_{run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"summary": report["summary"], "report_path": str(output_path)},
            ensure_ascii=True,
        )
    )
    if report["summary"]["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
