from __future__ import annotations

import math


def recall_at_k(ranks: list[int | None], k: int) -> float:
    """计算 Recall@K。"""

    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return hits / len(ranks)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    """计算 MRR。"""

    if not ranks:
        return 0.0
    score = 0.0
    for rank in ranks:
        if rank is None or rank <= 0:
            continue
        score += 1.0 / rank
    return score / len(ranks)


def percentile(values: list[int], p: float) -> int:
    """计算分位数（简单实现）。"""

    if not values:
        return 0
    sorted_values = sorted(values)
    index = max(0, math.ceil((p / 100) * len(sorted_values)) - 1)
    return sorted_values[index]
