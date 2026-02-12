from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalSetRecord:
    """评测集记录。"""

    eval_set_id: str
    name: str
    description: str | None
    created_at: str
