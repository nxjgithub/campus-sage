"""运行时问答指标聚合，供监控接口快速查看联调健康度。"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models import MessageRecord

_CLARIFICATION_ACTIONS = {"add_context", "rewrite_question", "verify_kb_scope"}
_FRESHNESS_HINT_PREFIX = "提示：问题涉及时效"


@dataclass(slots=True)
class RagRuntimeMetrics:
    """RAG 运行时指标快照。"""

    sample_size: int
    refusal_count: int
    clarification_count: int
    freshness_warning_count: int
    citation_covered_count: int
    refusal_rate: float
    clarification_rate: float
    freshness_warning_rate: float
    citation_coverage_rate: float


def build_rag_runtime_metrics(messages: list[MessageRecord]) -> RagRuntimeMetrics:
    """从助手消息中聚合核心联调指标。"""

    sample_size = len(messages)
    refusal_count = 0
    clarification_count = 0
    freshness_warning_count = 0
    citation_covered_count = 0

    for message in messages:
        if message.refusal:
            refusal_count += 1
            if _contains_clarification_action(message.next_steps):
                clarification_count += 1
        else:
            if message.citations:
                citation_covered_count += 1
        if _contains_freshness_warning(message):
            freshness_warning_count += 1

    return RagRuntimeMetrics(
        sample_size=sample_size,
        refusal_count=refusal_count,
        clarification_count=clarification_count,
        freshness_warning_count=freshness_warning_count,
        citation_covered_count=citation_covered_count,
        refusal_rate=_ratio(refusal_count, sample_size),
        clarification_rate=_ratio(clarification_count, sample_size),
        freshness_warning_rate=_ratio(freshness_warning_count, sample_size),
        citation_coverage_rate=_ratio(citation_covered_count, sample_size),
    )


def _contains_clarification_action(next_steps: list[dict[str, object]]) -> bool:
    """识别是否属于澄清型拒答。"""

    for item in next_steps:
        action = item.get("action")
        if isinstance(action, str) and action in _CLARIFICATION_ACTIONS:
            return True
    return False


def _contains_freshness_warning(message: MessageRecord) -> bool:
    """识别是否带有时效核验提示。"""

    if _FRESHNESS_HINT_PREFIX in message.content:
        return True
    for item in message.next_steps:
        action = item.get("action")
        if action == "check_official_source":
            return True
    return False


def _ratio(numerator: int, denominator: int) -> float:
    """计算比率并统一保留 4 位小数。"""

    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
