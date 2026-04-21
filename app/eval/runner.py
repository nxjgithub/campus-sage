from __future__ import annotations

import time
from app.core.settings import Settings
from app.eval.dto import (
    EvalCandidatePreview,
    EvalItem,
    EvalItemResult,
    EvalResult,
    EvalSet,
)
from app.eval.metrics import mean_reciprocal_rank, percentile, recall_at_k
from app.rag.embedding import Embedder, get_embedder
from app.rag.retrieval_policy import resolve_search_topk
from app.rag.reranker import SimpleReranker
from app.rag.vector_store import VectorHit, VectorStore, get_vector_store


def run_eval(
    *,
    kb_id: str,
    eval_set: EvalSet,
    topk: int,
    settings: Settings,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    rerank_enabled: bool = False,
    threshold: float | None = None,
) -> EvalResult:
    """运行评测并返回汇总指标。"""

    result, _ = run_eval_with_details(
        kb_id=kb_id,
        eval_set=eval_set,
        topk=topk,
        settings=settings,
        embedder=embedder,
        vector_store=vector_store,
        rerank_enabled=rerank_enabled,
        threshold=threshold,
    )
    return result


def run_eval_with_details(
    *,
    kb_id: str,
    eval_set: EvalSet,
    topk: int,
    settings: Settings,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    rerank_enabled: bool = False,
    threshold: float | None = None,
) -> tuple[EvalResult, list[EvalItemResult]]:
    """运行评测并同时返回汇总与逐题明细。"""

    item_results = evaluate_items(
        kb_id=kb_id,
        eval_set=eval_set,
        topk=topk,
        settings=settings,
        embedder=embedder,
        vector_store=vector_store,
        rerank_enabled=rerank_enabled,
        threshold=threshold,
    )
    ranks = [item.rank for item in item_results]
    durations = [item.retrieve_ms for item in item_results]
    return _build_metrics(ranks, durations, topk), item_results


def evaluate_items(
    *,
    kb_id: str,
    eval_set: EvalSet,
    topk: int,
    settings: Settings,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
    rerank_enabled: bool = False,
    threshold: float | None = None,
) -> list[EvalItemResult]:
    """评测样本逐条执行并返回明细。"""

    embedder = embedder or get_embedder(settings)
    vector_store = vector_store or get_vector_store(settings)
    reranker = SimpleReranker()

    results: list[EvalItemResult] = []
    search_topk = resolve_search_topk(
        final_topk=topk,
        rerank_enabled=rerank_enabled,
        rerank_candidate_multiplier=settings.rag_rerank_candidate_multiplier,
        rerank_candidate_cap=settings.rag_rerank_candidate_cap,
    )
    for item in eval_set.items:
        start = time.perf_counter()
        query_vector = embedder.embed_query(item.question)
        raw_hits = vector_store.search(kb_id=kb_id, query_vector=query_vector, topk=search_topk)
        raw_rank = _first_match_rank(raw_hits, item)
        threshold_hits = raw_hits
        if threshold is not None:
            threshold_hits = [hit for hit in threshold_hits if hit.score >= threshold]
        threshold_rank = _first_match_rank(threshold_hits, item)
        final_hits = threshold_hits
        if rerank_enabled and final_hits:
            final_hits = reranker.rerank(item.question, final_hits)
        final_hits = final_hits[:topk]
        duration = int((time.perf_counter() - start) * 1000)
        rank = _first_match_rank(final_hits, item)
        results.append(
            EvalItemResult(
                question=item.question,
                gold_doc_id=item.gold_doc_id,
                gold_doc_name=item.gold_doc_name,
                rank=rank,
                raw_rank=raw_rank,
                threshold_rank=threshold_rank,
                retrieve_ms=duration,
                raw_hit_count=len(raw_hits),
                threshold_hit_count=len(threshold_hits),
                final_hit_count=len(final_hits),
                top_candidates=_build_candidate_previews(raw_hits, item),
            )
        )
    return results


def _build_candidate_previews(
    hits: list[VectorHit],
    item: EvalItem,
    limit: int = 3,
) -> list[EvalCandidatePreview]:
    """生成前几个候选摘要，便于离线排障。"""

    previews: list[EvalCandidatePreview] = []
    for index, hit in enumerate(hits[: max(0, limit)], start=1):
        payload = hit.payload
        previews.append(
            EvalCandidatePreview(
                rank=index,
                doc_id=payload.get("doc_id"),
                doc_name=payload.get("doc_name"),
                score=hit.score,
                matched=_match_hit(hit, item),
            )
        )
    return previews


def _build_metrics(
    ranks: list[int | None],
    durations: list[int],
    topk: int,
) -> EvalResult:
    """基于命中排名与耗时构建评测指标。"""

    return EvalResult(
        recall_at_k=recall_at_k(ranks, topk),
        mrr=mean_reciprocal_rank(ranks),
        avg_ms=int(sum(durations) / len(durations)) if durations else 0,
        p95_ms=percentile(durations, 95),
        samples=len(ranks),
    )


def _first_match_rank(hits: list[VectorHit], item: EvalItem) -> int | None:
    """找到首个命中文档的排名，从 1 开始。"""

    for index, hit in enumerate(hits, start=1):
        if _match_hit(hit, item):
            return index
    return None


def _match_hit(hit: VectorHit, item: EvalItem) -> bool:
    """判断检索结果是否命中标准证据。"""

    payload = hit.payload
    if item.gold_doc_id:
        if payload.get("doc_id") != item.gold_doc_id:
            return False
    elif item.gold_doc_name:
        if payload.get("doc_name") != item.gold_doc_name:
            return False
    else:
        return False
    if item.gold_page_start is None:
        return True
    page_start = payload.get("page_start")
    page_end = payload.get("page_end") or page_start
    if page_start is None:
        return False
    return _overlap(
        page_start,
        page_end or page_start,
        item.gold_page_start,
        item.gold_page_end or item.gold_page_start,
    )


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """判断页码区间是否重叠。"""

    return max(a_start, b_start) <= min(a_end, b_end)
