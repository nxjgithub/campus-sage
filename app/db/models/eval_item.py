from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalItemRecord:
    """评测样本记录。"""

    eval_item_id: str
    eval_set_id: str
    question: str
    gold_doc_id: str | None
    gold_page_start: int | None
    gold_page_end: int | None
    tags_json: str | None
    created_at: str
