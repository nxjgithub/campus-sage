from __future__ import annotations

from app.core.utils import utc_now_iso
from app.db.models import MessageRecord
from app.rag.runtime_metrics import build_rag_runtime_metrics


def test_build_rag_runtime_metrics_empty() -> None:
    metrics = build_rag_runtime_metrics([])
    assert metrics.sample_size == 0
    assert metrics.refusal_rate == 0.0
    assert metrics.clarification_rate == 0.0
    assert metrics.freshness_warning_rate == 0.0
    assert metrics.citation_coverage_rate == 0.0


def test_build_rag_runtime_metrics_mixed_cases() -> None:
    messages = [
        _assistant_message(
            refusal=True,
            next_steps=[{"action": "add_context"}],
        ),
        _assistant_message(
            refusal=True,
            next_steps=[{"action": "check_official_source"}],
        ),
        _assistant_message(
            refusal=False,
            content="回答正文\n\n提示：问题涉及时效，建议核验最新公告。",
            citations=[{"citation_id": 1}],
        ),
        _assistant_message(refusal=False),
    ]
    metrics = build_rag_runtime_metrics(messages)
    assert metrics.sample_size == 4
    assert metrics.refusal_count == 2
    assert metrics.clarification_count == 1
    assert metrics.freshness_warning_count == 2
    assert metrics.citation_covered_count == 1
    assert metrics.refusal_rate == 0.5
    assert metrics.clarification_rate == 0.25
    assert metrics.freshness_warning_rate == 0.5
    assert metrics.citation_coverage_rate == 0.25


def _assistant_message(
    *,
    refusal: bool,
    content: str = "测试消息",
    next_steps: list[dict[str, object]] | None = None,
    citations: list[dict[str, object]] | None = None,
) -> MessageRecord:
    return MessageRecord(
        message_id="msg_test",
        conversation_id="conv_test",
        role="assistant",
        content=content,
        refusal=refusal,
        refusal_reason="LOW_COVERAGE" if refusal else None,
        timing={"total_ms": 10},
        suggestions=[],
        next_steps=next_steps or [],
        citations=citations or [],
        created_at=utc_now_iso(),
    )
