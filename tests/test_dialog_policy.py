from __future__ import annotations

from app.core.utils import utc_now_iso
from app.db.models import MessageRecord
from app.rag.dialog_policy import (
    analyze_intent,
    build_dialog_state,
    build_freshness_notice,
    extract_slots,
)
from app.rag.dto import CitationDTO


def test_build_dialog_state_marks_pending_clarification() -> None:
    messages = [
        _message(role="user", content="补考申请条件是什么？"),
        _message(
            role="assistant",
            content="当前证据不足",
            refusal=True,
            next_steps=[
                {
                    "action": "add_context",
                    "label": "补充条件",
                    "detail": "请补充学院和年级",
                    "value": "学院/年级",
                }
            ],
        ),
    ]
    state = build_dialog_state(messages)
    assert state.turn_count == 1
    assert state.last_user_question == "补考申请条件是什么？"
    assert state.pending_clarification is True


def test_analyze_intent_smalltalk_returns_early_refusal() -> None:
    state = build_dialog_state([])
    decision = analyze_intent("你好", state)
    assert decision.intent == "smalltalk"
    assert decision.early_refusal is True
    assert decision.refusal_reason == "LOW_COVERAGE"
    assert decision.next_steps


def test_analyze_intent_asks_for_clarification_on_ambiguous_question() -> None:
    state = build_dialog_state([])
    decision = analyze_intent("这个怎么办", state)
    assert decision.intent == "clarification"
    assert decision.early_refusal is True
    assert decision.refusal_reason == "LOW_COVERAGE"
    assert any(step.action == "add_context" for step in decision.next_steps)


def test_analyze_intent_rewrites_followup_query() -> None:
    history = [_message(role="user", content="补考申请条件是什么？")]
    state = build_dialog_state(history)
    decision = analyze_intent("那时间呢", state)
    assert decision.intent == "policy_query"
    assert decision.early_refusal is False
    assert decision.retrieval_query.startswith("补考申请条件是什么")


def test_analyze_intent_keeps_clarification_for_underspecified_followup() -> None:
    history = [_message(role="user", content="补考申请条件是什么？")]
    state = build_dialog_state(history)
    decision = analyze_intent("这个怎么办", state)
    assert decision.intent == "clarification"
    assert decision.early_refusal is True
    assert any(step.action == "add_context" for step in decision.next_steps)


def test_analyze_intent_prefers_policy_query_when_topic_is_clear() -> None:
    state = build_dialog_state([])
    decision = analyze_intent("本科生补考流程和申请材料是什么？", state)
    assert decision.intent == "policy_query"
    assert decision.early_refusal is False
    assert decision.slots["topic"] == "补考与重修"
    assert decision.slots["role"] == "本科生"


def test_analyze_intent_prefers_policy_query_for_admission_notice() -> None:
    state = build_dialog_state([])
    decision = analyze_intent("四川轻化工大学宜宾校区5153报考点2025年网报公告有哪些信息？", state)
    assert decision.intent == "policy_query"
    assert decision.early_refusal is False
    assert decision.slots["topic"] == "招生与报考"


def test_extract_slots_from_question_and_history() -> None:
    slots = extract_slots(
        question="本科生补考流程是什么？",
        history_text="2026年3月需要提交吗",
    )
    assert slots["topic"] == "补考与重修"
    assert slots["role"] == "本科生"
    assert "time_hint" in slots


def test_build_freshness_notice_for_latest_question() -> None:
    warning, source_uri = build_freshness_notice(
        question="最新补考申请条件是什么？",
        citations=[_citation(published_at="2020-01-01")],
        stale_days=365,
    )
    assert warning is not None
    assert "2020-01-01" in warning
    assert source_uri == "https://example.edu/policy"


def test_build_freshness_notice_skips_non_latest_question() -> None:
    warning, source_uri = build_freshness_notice(
        question="补考申请条件是什么？",
        citations=[_citation(published_at="2020-01-01")],
        stale_days=365,
    )
    assert warning is None
    assert source_uri is None


def _message(
    role: str,
    content: str,
    refusal: bool = False,
    next_steps: list[dict[str, object]] | None = None,
) -> MessageRecord:
    return MessageRecord(
        message_id=f"msg_{role}",
        conversation_id="conv_test",
        role=role,
        content=content,
        refusal=refusal,
        refusal_reason="LOW_COVERAGE" if refusal else None,
        timing=None,
        suggestions=[],
        next_steps=next_steps or [],
        citations=[],
        created_at=utc_now_iso(),
    )


def _citation(published_at: str) -> CitationDTO:
    return CitationDTO(
        citation_id=1,
        doc_id="doc_1",
        doc_name="政策文档",
        doc_version=None,
        published_at=published_at,
        source_uri="https://example.edu/policy",
        page_start=1,
        page_end=1,
        section_path="考试管理/补考",
        chunk_id="chunk_1",
        snippet="补考申请条件",
        score=0.9,
    )
