"""多轮对话策略：意图识别、槽位抽取、澄清路由与时效提示。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db.models import MessageRecord
from app.rag.dto import CitationDTO, NextStepDTO

_SMALLTALK_KEYWORDS = (
    "你好",
    "您好",
    "hi",
    "hello",
    "在吗",
    "谢谢",
    "thanks",
    "再见",
    "bye",
)

_AMBIGUOUS_REFERENCES = ("这个", "那个", "它", "这项", "该项", "上述", "上面")

_POLICY_INTENT_KEYWORDS = (
    "流程",
    "步骤",
    "条件",
    "要求",
    "材料",
    "多久",
    "时间",
    "截止",
    "怎么办",
    "如何",
    "申请",
    "办理",
    "规定",
    "政策",
    "公告",
    "通知",
    "招生",
    "报考",
    "网报",
    "报名",
    "复试",
    "分数线",
    "录取",
)

_TOPIC_GROUPS: dict[str, tuple[str, ...]] = {
    "补考与重修": ("补考", "重修", "缓考", "考试"),
    "选课与学分": ("选课", "退课", "学分", "课程"),
    "转专业": ("转专业", "专业分流", "转入"),
    "奖助学金": ("奖学金", "助学金", "助学贷款"),
    "毕业审核": ("毕业", "论文", "答辩", "学位"),
    "招生与报考": ("招生", "报考", "复试", "网报", "报名", "分数线", "录取", "考点"),
}

_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "本科生": ("本科生", "本科", "大一", "大二", "大三", "大四"),
    "研究生": ("研究生", "硕士", "博士"),
    "留学生": ("留学生", "国际学生"),
    "考生": ("考生",),
}

_FRESHNESS_KEYWORDS = (
    "最新",
    "当前",
    "现在",
    "今年",
    "近期",
    "recent",
    "latest",
    "up-to-date",
)

_CLARIFICATION_ACTIONS = {"add_context", "rewrite_question", "verify_kb_scope"}

_LIGHTWEIGHT_MODEL_WEIGHTS: dict[str, dict[str, float]] = {
    "policy_query": {
        "申请": 1.2,
        "流程": 1.1,
        "条件": 1.1,
        "要求": 1.0,
        "办理": 1.0,
        "补考": 1.1,
        "学分": 0.9,
        "材料": 0.9,
        "政策": 1.0,
        "公告": 1.0,
        "通知": 1.0,
        "招生": 1.2,
        "报考": 1.2,
        "网报": 1.1,
        "报名": 1.0,
        "复试": 1.1,
        "分数线": 1.1,
        "录取": 1.1,
        "考点": 1.0,
    },
    "clarification": {
        "这个": 1.2,
        "那个": 1.2,
        "它": 0.8,
        "怎么办": 0.7,
        "怎么弄": 0.8,
        "咋办": 0.8,
    },
    "smalltalk": {
        "你好": 1.5,
        "在吗": 1.4,
        "谢谢": 1.2,
        "hello": 1.3,
        "hi": 1.1,
        "bye": 1.1,
    },
}


@dataclass(slots=True)
class DialogState:
    """多轮对话状态摘要。"""

    turn_count: int
    last_user_question: str | None
    pending_clarification: bool
    history_text: str


@dataclass(slots=True)
class IntentDecision:
    """意图识别决策结果。"""

    intent: str
    normalized_question: str
    retrieval_query: str
    slots: dict[str, str] = field(default_factory=dict)
    early_refusal: bool = False
    refusal_reason: str | None = None
    suggestions: list[str] = field(default_factory=list)
    next_steps: list[NextStepDTO] = field(default_factory=list)


@dataclass(slots=True)
class IntentScore:
    """承载融合打分结果，便于调试与扩展。"""

    intent: str
    score: float


def build_dialog_state(messages: list[MessageRecord]) -> DialogState:
    """根据历史消息构建对话状态。"""

    user_questions = [item.content for item in messages if item.role == "user" and item.content.strip()]
    pending_clarification = False
    if messages:
        last_message = messages[-1]
        if last_message.role == "assistant" and last_message.refusal:
            pending_clarification = _has_clarification_action(last_message.next_steps)
    return DialogState(
        turn_count=len(user_questions),
        last_user_question=user_questions[-1] if user_questions else None,
        pending_clarification=pending_clarification,
        history_text="\n".join(user_questions[-6:]),
    )


def analyze_intent(question: str, state: DialogState) -> IntentDecision:
    """识别意图并给出路由决策。"""

    normalized = _normalize(question)
    slots = extract_slots(normalized, state.history_text)
    if not normalized:
        return _clarification_decision(
            normalized_question=normalized,
            slots=slots,
            detail_value="事项/对象/条件/时间/材料",
        )
    if _is_smalltalk(normalized):
        return _smalltalk_decision(normalized_question=normalized, slots=slots)

    scored = _score_intents(normalized, slots, state)
    intent = _pick_intent(scored)
    if intent == "smalltalk":
        return _smalltalk_decision(normalized_question=normalized, slots=slots)
    if intent == "clarification" or _need_clarification(normalized, slots, state):
        return _clarification_decision(
            normalized_question=normalized,
            slots=slots,
            detail_value="学院/年级/身份/业务事项",
        )

    retrieval_query = _rewrite_followup_query(normalized, state)
    return IntentDecision(
        intent="policy_query",
        normalized_question=normalized,
        retrieval_query=retrieval_query,
        slots=slots,
    )


def extract_slots(question: str, history_text: str) -> dict[str, str]:
    """抽取业务槽位（主题/角色/时间）。"""

    merged = f"{question}\n{history_text}".strip()
    slots: dict[str, str] = {}

    topic = _extract_topic(merged)
    if topic is not None:
        slots["topic"] = topic

    role = _extract_role(merged)
    if role is not None:
        slots["role"] = role

    time_hint = _extract_time_hint(merged)
    if time_hint is not None:
        slots["time_hint"] = time_hint

    return slots


def build_freshness_notice(
    question: str,
    citations: list[CitationDTO],
    stale_days: int,
) -> tuple[str | None, str | None]:
    """根据问题与引用生成时效提示。"""

    if not _requires_freshness(question):
        return None, None
    source_uri = _pick_source_uri(citations)
    published_dates = [_parse_published_date(item.published_at) for item in citations]
    available_dates = [item for item in published_dates if item is not None]
    if not available_dates:
        return "问题涉及时效，但当前证据缺少可用发布日期，建议核验最新官方通知。", source_uri
    latest_date = max(available_dates)
    age_days = (datetime.now(UTC).date() - latest_date.date()).days
    if age_days <= max(0, stale_days):
        return None, source_uri
    return (
        f"问题涉及时效，当前最新证据发布日期为 {latest_date.date().isoformat()}，请核验是否已有更新。",
        source_uri,
    )


def _smalltalk_decision(normalized_question: str, slots: dict[str, str]) -> IntentDecision:
    """构造闲聊场景的拒答决策。"""

    return IntentDecision(
        intent="smalltalk",
        normalized_question=normalized_question,
        retrieval_query=normalized_question,
        slots=slots,
        early_refusal=True,
        refusal_reason="LOW_COVERAGE",
        suggestions=[
            "当前系统主要用于校园制度问答，请提供明确业务问题。",
            "可按“事项 + 对象 + 条件/时间/材料”的格式提问。",
        ],
        next_steps=[
            NextStepDTO(
                action="rewrite_question",
                label="改写问题",
                detail="请将问句改为校园业务办理类问题，例如“补考申请条件是什么”。",
                value="事项 + 对象 + 条件/时间/材料",
            ),
            NextStepDTO(
                action="verify_kb_scope",
                label="确认知识库范围",
                detail="当前知识库侧重制度与流程，不覆盖闲聊类内容。",
                value=None,
            ),
        ],
    )


def _score_intents(text: str, slots: dict[str, str], state: DialogState) -> list[IntentScore]:
    """融合规则分与轻量模型分，输出三类意图得分。"""

    rule_scores = {"policy_query": 0.0, "clarification": 0.0, "smalltalk": 0.0}
    has_topic = "topic" in slots
    mentions_policy = any(keyword in text for keyword in _POLICY_INTENT_KEYWORDS)
    has_ambiguous_reference = any(keyword in text for keyword in _AMBIGUOUS_REFERENCES)

    if has_topic:
        rule_scores["policy_query"] += 1.4
    if mentions_policy:
        rule_scores["policy_query"] += 1.0
    if text.endswith(("吗", "么", "？", "?")):
        rule_scores["policy_query"] += 0.2

    if len(text) <= 2:
        rule_scores["clarification"] += 1.6
    if has_ambiguous_reference:
        rule_scores["clarification"] += 1.2
    if state.pending_clarification and not has_topic:
        rule_scores["clarification"] += 0.8

    if _is_smalltalk(text):
        rule_scores["smalltalk"] += 1.8

    model_scores = _lightweight_model_scores(text)
    fused: list[IntentScore] = []
    for intent in ("policy_query", "clarification", "smalltalk"):
        score = rule_scores[intent] * 0.7 + model_scores[intent] * 0.3
        fused.append(IntentScore(intent=intent, score=score))
    return fused


def _lightweight_model_scores(text: str) -> dict[str, float]:
    """轻量模型打分：基于词项权重模拟线性分类器。"""

    logits: dict[str, float] = {"policy_query": 0.25, "clarification": 0.25, "smalltalk": 0.25}
    lowered = text.lower()
    for intent, weights in _LIGHTWEIGHT_MODEL_WEIGHTS.items():
        for keyword, weight in weights.items():
            if keyword in lowered:
                logits[intent] += weight
    return _softmax(logits)


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    """将线性分数归一化到概率空间，便于与规则分融合。"""

    max_logit = max(logits.values())
    exp_values = {key: math.exp(value - max_logit) for key, value in logits.items()}
    denominator = sum(exp_values.values())
    if denominator <= 0:
        return {key: 1 / len(exp_values) for key in exp_values}
    return {key: value / denominator for key, value in exp_values.items()}


def _pick_intent(scored: list[IntentScore]) -> str:
    """根据融合分选取最终意图，并对低置信度做保守兜底。"""

    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    top = ranked[0]
    second = ranked[1]
    if top.score < 0.4:
        return "clarification"
    if top.score - second.score < 0.08 and top.intent != "policy_query":
        return "clarification"
    return top.intent


def _clarification_decision(
    normalized_question: str,
    slots: dict[str, str],
    detail_value: str,
) -> IntentDecision:
    """构造澄清追问决策。"""

    return IntentDecision(
        intent="clarification",
        normalized_question=normalized_question,
        retrieval_query=normalized_question,
        slots=slots,
        early_refusal=True,
        refusal_reason="LOW_COVERAGE",
        suggestions=[
            "当前问题缺少关键上下文，建议补充业务对象与条件。",
            "可按“事项 + 对象 + 条件/时间/材料”的方式提问。",
        ],
        next_steps=[
            NextStepDTO(
                action="add_context",
                label="补充场景条件",
                detail="请补充学院、年级、身份和具体办理事项，再重新提问。",
                value=detail_value,
            ),
            NextStepDTO(
                action="rewrite_question",
                label="改写问题",
                detail="避免“这个/那个”这类指代词，改为可检索的完整问题。",
                value="事项 + 对象 + 条件/时间/材料",
            ),
        ],
    )


def _is_smalltalk(text: str) -> bool:
    """判断是否为闲聊意图。"""

    lowered = text.lower()
    if lowered in _SMALLTALK_KEYWORDS:
        return True
    if len(lowered) <= 6 and any(keyword in lowered for keyword in _SMALLTALK_KEYWORDS):
        return True
    return False


def _need_clarification(text: str, slots: dict[str, str], state: DialogState) -> bool:
    """判断是否需要先澄清。"""

    if len(text) <= 2:
        return True
    has_topic = "topic" in slots
    mentions_policy = any(keyword in text for keyword in _POLICY_INTENT_KEYWORDS)
    has_ambiguous_reference = any(keyword in text for keyword in _AMBIGUOUS_REFERENCES)
    if has_ambiguous_reference and not has_topic and not state.last_user_question:
        return True
    if mentions_policy and not has_topic:
        return True
    if state.pending_clarification and not has_topic and len(text) < 16:
        return True
    return False


def _rewrite_followup_query(text: str, state: DialogState) -> str:
    """对追问场景补全检索查询词。"""

    if not state.last_user_question:
        return text
    is_short_followup = len(text) <= 12
    has_ambiguous_reference = any(keyword in text for keyword in _AMBIGUOUS_REFERENCES)
    if not (is_short_followup or has_ambiguous_reference):
        return text
    if text == state.last_user_question:
        return text
    return f"{state.last_user_question}；补充问题：{text}"


def _extract_topic(text: str) -> str | None:
    """提取业务主题。"""

    for topic, keywords in _TOPIC_GROUPS.items():
        if any(keyword in text for keyword in keywords):
            return topic
    return None


def _extract_role(text: str) -> str | None:
    """提取用户角色线索。"""

    for role, keywords in _ROLE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return role
    return None


def _extract_time_hint(text: str) -> str | None:
    """提取时间线索。"""

    patterns = (
        r"(20\d{2}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)",
        r"(\d{1,2}月\d{1,2}日?)",
        r"(本学期|下学期|本周|下周|本月|下月|今年|明年)",
    )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return matched.group(1)
    return None


def _normalize(text: str) -> str:
    """标准化文本。"""

    return " ".join(text.strip().split())


def _has_clarification_action(next_steps: list[dict[str, object]]) -> bool:
    """判断拒答建议里是否包含澄清动作。"""

    for item in next_steps:
        action = item.get("action")
        if isinstance(action, str) and action in _CLARIFICATION_ACTIONS:
            return True
    return False


def _requires_freshness(question: str) -> bool:
    """判断问题是否带有明显时效诉求。"""

    lowered = question.lower()
    return any(keyword in lowered for keyword in _FRESHNESS_KEYWORDS)


def _parse_published_date(value: str | None) -> datetime | None:
    """解析发布日期。"""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    formats = ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")
    for fmt in formats:
        try:
            parsed = datetime.strptime(candidate, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pick_source_uri(citations: list[CitationDTO]) -> str | None:
    """提取可用来源链接。"""

    for item in citations:
        if item.source_uri is not None and item.source_uri.strip():
            return item.source_uri.strip()
    return None
