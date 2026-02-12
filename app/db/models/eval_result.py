from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalResultRecord:
    """评测逐条结果记录。"""

    run_result_id: str
    run_id: str
    eval_item_id: str
    hit: bool
    rank: int | None
    retrieve_ms: int | None
    notes: str | None
    created_at: str
