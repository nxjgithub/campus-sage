from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalRunRecord:
    """评测运行记录。"""

    run_id: str
    eval_set_id: str
    kb_id: str
    topk: int
    threshold: float | None
    rerank_enabled: bool
    metrics_json: str | None
    created_at: str
