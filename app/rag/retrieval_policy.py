from __future__ import annotations


def resolve_search_topk(
    *,
    final_topk: int,
    rerank_enabled: bool,
    rerank_candidate_multiplier: int,
    rerank_candidate_cap: int,
) -> int:
    """计算实际检索候选数，重排开启时适度放大候选池。"""

    normalized_topk = max(1, final_topk)
    if not rerank_enabled:
        return normalized_topk
    normalized_multiplier = max(1, rerank_candidate_multiplier)
    normalized_cap = max(normalized_topk, rerank_candidate_cap)
    return min(normalized_topk * normalized_multiplier, normalized_cap)
