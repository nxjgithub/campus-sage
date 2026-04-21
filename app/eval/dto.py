from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalItem:
    """单条评测样本。"""

    question: str
    gold_doc_id: str | None
    gold_page_start: int | None
    gold_page_end: int | None
    gold_doc_name: str | None = None


@dataclass(slots=True)
class EvalSet:
    """评测集结构。"""

    name: str
    items: list[EvalItem]


@dataclass(slots=True)
class EvalResult:
    """评测结果汇总。"""

    recall_at_k: float
    mrr: float
    avg_ms: int
    p95_ms: int
    samples: int


@dataclass(slots=True)
class EvalCandidatePreview:
    """评测明细中的候选摘要。"""

    rank: int
    doc_id: str | None
    doc_name: str | None
    score: float | None
    matched: bool


@dataclass(slots=True)
class EvalItemResult:
    """评测单条结果。"""

    question: str
    gold_doc_id: str | None
    gold_doc_name: str | None
    rank: int | None
    raw_rank: int | None
    threshold_rank: int | None
    retrieve_ms: int
    raw_hit_count: int
    threshold_hit_count: int
    final_hit_count: int
    top_candidates: list[EvalCandidatePreview]
