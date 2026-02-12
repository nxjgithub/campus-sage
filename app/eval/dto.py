from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalItem:
    """单条评测样本。"""

    question: str
    gold_doc_id: str
    gold_page_start: int | None
    gold_page_end: int | None


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
class EvalItemResult:
    """评测单条结果。"""

    rank: int | None
    retrieve_ms: int
