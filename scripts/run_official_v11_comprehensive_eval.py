from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.rag.vector_store import VectorHit
from scripts.run_official_v11_fast_eval import (
    LocalEmbeddingClient,
    build_index_chunks,
    build_rerank_text,
    cosine,
    first_match_rank,
)


@dataclass(slots=True)
class MethodResult:
    """单个检索方法在一个问题上的结果。"""

    question: str
    question_type: str
    gold_doc_name: str | None
    method: str
    rank: int | None
    top_score: float | None
    elapsed_ms: int
    top_docs: list[str]
    top_chunk_ids: list[str]
    context_chars: int
    citation_ready: bool


class BM25Index:
    """面向正式文件短问题的轻量 BM25 基线。"""

    def __init__(self, chunks: list[Any], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._doc_tokens: list[list[str]] = []
        self._doc_tf: list[Counter[str]] = []
        self._df: Counter[str] = Counter()
        for chunk in chunks:
            tokens = tokenize(build_text(chunk.payload))
            tf = Counter(tokens)
            self._doc_tokens.append(tokens)
            self._doc_tf.append(tf)
            self._df.update(tf.keys())
        self._avg_len = sum(len(tokens) for tokens in self._doc_tokens) / max(1, len(self._doc_tokens))

    def search(self, query: str, topk: int) -> list[VectorHit]:
        """按 BM25 分数返回候选片段。"""

        scores = self.score_all(query)
        indexed = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return [
            VectorHit(score=float(score), payload=self._chunks[index].payload)
            for index, score in indexed[:topk]
        ]

    def score_all(self, query: str) -> list[float]:
        """计算查询对全部片段的 BM25 分数。"""

        query_terms = tokenize(query)
        if not query_terms:
            return [0.0 for _ in self._chunks]
        total_docs = len(self._chunks)
        scores: list[float] = []
        for tokens, tf in zip(self._doc_tokens, self._doc_tf, strict=True):
            doc_len = len(tokens)
            score = 0.0
            for term in query_terms:
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                doc_freq = self._df.get(term, 0)
                idf = math.log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
                denom = freq + self._k1 * (1 - self._b + self._b * doc_len / max(1.0, self._avg_len))
                score += idf * freq * (self._k1 + 1) / denom
            scores.append(score)
        return scores


class CrossEncoderReranker:
    """使用本地 CrossEncoder 输出重排分数。"""

    def __init__(self, model_name: str, batch_size: int) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name, device="cpu", local_files_only=True)
        self._batch_size = max(1, batch_size)

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """按 sigmoid 后的 CrossEncoder 分数重排候选。"""

        if not hits:
            return []
        pairs = [[question, build_rerank_text(hit)] for hit in hits]
        raw_scores = self._model.predict(pairs, batch_size=self._batch_size, show_progress_bar=False)
        scored = [
            VectorHit(score=sigmoid(float(score)), payload=hit.payload)
            for hit, score in zip(hits, raw_scores, strict=True)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored


def main() -> None:
    """运行 V11 正式文件综合检索评测。"""

    parser = argparse.ArgumentParser(description="运行 V11 正式文件综合评测")
    parser.add_argument("--manifest-file", default="docs/examples/official_formal_corpus_v11_manifest.json")
    parser.add_argument("--eval-file", default="docs/examples/eval_set_official_formal_v11.json")
    parser.add_argument("--output-file", default="outputs/eval_official_formal_v11_fast/comprehensive_eval.json")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--rerank-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", str(ROOT_DIR / "data" / "hf_cache"))
    manifest = json.loads((ROOT_DIR / args.manifest_file).read_text(encoding="utf-8"))
    eval_set = json.loads((ROOT_DIR / args.eval_file).read_text(encoding="utf-8"))
    questions = eval_set.get("items") or []

    embedding = LocalEmbeddingClient(args.embedding_model, args.batch_size)
    reranker = CrossEncoderReranker(args.rerank_model, args.batch_size)

    build_start = time.perf_counter()
    chunks, doc_stats = build_index_chunks(
        manifest=manifest,
        embedding=embedding,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    bm25 = BM25Index(chunks)
    query_vectors = embedding.embed_texts([str(item["question"]) for item in questions])
    build_ms = int((time.perf_counter() - build_start) * 1000)

    method_results: list[MethodResult] = []
    for index, (item, query_vector) in enumerate(zip(questions, query_vectors, strict=True), start=1):
        question = str(item["question"])
        gold_doc_name = item.get("gold_doc_name")
        question_type = str(item.get("question_type") or "unknown")

        vector_hits_30 = vector_search(chunks, query_vector, 30)
        bm25_hits_30 = bm25.search(question, 30)
        hybrid_hits_30 = hybrid_search(chunks, query_vector, bm25.score_all(question), 30)

        add_result(method_results, question, question_type, gold_doc_name, "bm25@5", bm25_hits_30[:5], 0)
        add_result(method_results, question, question_type, gold_doc_name, "vector@5", vector_hits_30[:5], 0)
        add_result(method_results, question, question_type, gold_doc_name, "hybrid@5", hybrid_hits_30[:5], 0)

        for candidate_topk in [5, 10, 20, 30]:
            start = time.perf_counter()
            reranked = reranker.rerank(question, vector_hits_30[:candidate_topk])[:5]
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            add_result(
                method_results,
                question,
                question_type,
                gold_doc_name,
                f"vector_rerank_c{candidate_topk}@5",
                reranked,
                elapsed_ms,
            )

        start = time.perf_counter()
        hybrid_reranked = reranker.rerank(question, hybrid_hits_30[:20])[:5]
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        add_result(
            method_results,
            question,
            question_type,
            gold_doc_name,
            "hybrid_rerank_c20@5",
            hybrid_reranked,
            elapsed_ms,
        )

        start = time.perf_counter()
        bm25_reranked = reranker.rerank(question, bm25_hits_30[:20])[:5]
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        add_result(
            method_results,
            question,
            question_type,
            gold_doc_name,
            "bm25_rerank_c20@5",
            bm25_reranked,
            elapsed_ms,
        )

        if index % 10 == 0 or index == len(questions):
            print(f"evaluated {index}/{len(questions)}", flush=True)

    payload = build_report(
        manifest=manifest,
        eval_set=eval_set,
        doc_stats=doc_stats,
        chunk_count=len(chunks),
        build_ms=build_ms,
        method_results=method_results,
        environment={
            "embedding_model": args.embedding_model,
            "rerank_model": args.rerank_model,
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap,
            "batch_size": args.batch_size,
        },
    )
    output_file = ROOT_DIR / args.output_file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["console"], ensure_ascii=False, indent=2))


def tokenize(text: str) -> list[str]:
    """把中英文混合文本切成适合 BM25 的轻量词元。"""

    normalized = text.lower()
    words = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized)
    if not words:
        words = [char for char in normalized if not char.isspace()]
    cjk_chars = [token for token in words if re.fullmatch(r"[\u4e00-\u9fff]", token)]
    bigrams = [left + right for left, right in zip(cjk_chars, cjk_chars[1:])]
    return words + bigrams


def build_text(payload: dict[str, Any]) -> str:
    """组合片段的文件名、章节和正文。"""

    parts = [
        str(payload.get("doc_name") or ""),
        str(payload.get("section_path") or ""),
        str(payload.get("text") or ""),
    ]
    return "\n".join(part for part in parts if part.strip())


def vector_search(chunks: list[Any], query_vector: list[float], topk: int) -> list[VectorHit]:
    """执行本地向量检索。"""

    hits = [
        VectorHit(score=cosine(query_vector, chunk.vector), payload=chunk.payload)
        for chunk in chunks
    ]
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:topk]


def hybrid_search(
    chunks: list[Any],
    query_vector: list[float],
    bm25_scores: list[float],
    topk: int,
) -> list[VectorHit]:
    """融合向量分数与 BM25 分数。"""

    vector_scores = [cosine(query_vector, chunk.vector) for chunk in chunks]
    norm_vector = normalize(vector_scores)
    norm_bm25 = normalize(bm25_scores)
    hits = [
        VectorHit(
            score=0.65 * norm_vector[index] + 0.35 * norm_bm25[index],
            payload=chunk.payload,
        )
        for index, chunk in enumerate(chunks)
    ]
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:topk]


def normalize(values: list[float]) -> list[float]:
    """把分数归一化到 0 到 1。"""

    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    if math.isclose(max_value, min_value):
        return [0.0 for _ in values]
    return [(value - min_value) / (max_value - min_value) for value in values]


def add_result(
    results: list[MethodResult],
    question: str,
    question_type: str,
    gold_doc_name: str | None,
    method: str,
    hits: list[VectorHit],
    elapsed_ms: int,
) -> None:
    """记录单个方法的评测结果。"""

    results.append(
        MethodResult(
            question=question,
            question_type=question_type,
            gold_doc_name=gold_doc_name,
            method=method,
            rank=first_match_rank(hits, gold_doc_name),
            top_score=hits[0].score if hits else None,
            elapsed_ms=elapsed_ms,
            top_docs=[str(hit.payload.get("doc_name") or "") for hit in hits],
            top_chunk_ids=[str(hit.payload.get("chunk_id") or "") for hit in hits],
            context_chars=sum(len(str(hit.payload.get("text") or "")) for hit in hits),
            citation_ready=all(has_citation_location(hit.payload) for hit in hits),
        )
    )


def has_citation_location(payload: dict[str, Any]) -> bool:
    """判断证据是否满足引用定位的最低要求。"""

    has_doc = bool(str(payload.get("doc_name") or "").strip())
    has_text = bool(str(payload.get("text") or "").strip())
    has_page = payload.get("page_start") is not None or payload.get("page_end") is not None
    has_section = bool(str(payload.get("section_path") or "").strip())
    return has_doc and has_text and (has_page or has_section)


def build_report(
    *,
    manifest: dict[str, Any],
    eval_set: dict[str, Any],
    doc_stats: list[dict[str, Any]],
    chunk_count: int,
    build_ms: int,
    method_results: list[MethodResult],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """汇总综合实验结果。"""

    by_method: dict[str, list[MethodResult]] = defaultdict(list)
    for result in method_results:
        by_method[result.method].append(result)

    method_summary = {
        method: summarize_method(results)
        for method, results in sorted(by_method.items())
    }
    recommended = by_method["vector_rerank_c20@5"]
    threshold_results = summarize_thresholds(recommended, [0.50, 0.55, 0.60, 0.65, 0.70])
    type_summary = summarize_by_type(recommended)
    hard_subset = [item for item in by_method["vector@5"] if item.gold_doc_name and item.rank != 1]
    hard_questions = {
        item.question
        for item in hard_subset
    }
    hard_results = [
        item for item in recommended if item.question in hard_questions and item.gold_doc_name
    ]
    payload = {
        "eval_set": eval_set.get("name"),
        "source_dir": manifest.get("source_dir"),
        "document_count": manifest.get("document_count"),
        "skipped_count": len(manifest.get("skipped") or []),
        "question_count": len(eval_set.get("items") or []),
        "in_scope_question_count": sum(1 for item in eval_set.get("items") or [] if item.get("gold_doc_name")),
        "out_of_scope_question_count": sum(1 for item in eval_set.get("items") or [] if not item.get("gold_doc_name")),
        "chunk_count": chunk_count,
        "total_chars": sum(item["char_count"] for item in doc_stats),
        "build_ms": build_ms,
        "environment": environment,
        "method_summary": method_summary,
        "type_summary": type_summary,
        "hard_subset_summary": summarize_method(hard_results),
        "threshold_results": threshold_results,
        "answerability": summarize_answerability(recommended),
        "items": [asdict(result) for result in method_results],
    }
    payload["console"] = {
        "dataset": {
            "documents": payload["document_count"],
            "chunks": payload["chunk_count"],
            "questions": payload["question_count"],
            "in_scope": payload["in_scope_question_count"],
            "out_of_scope": payload["out_of_scope_question_count"],
        },
        "method_summary": method_summary,
        "type_summary": type_summary,
        "hard_subset_summary": payload["hard_subset_summary"],
        "threshold_results": threshold_results,
        "answerability": payload["answerability"],
    }
    return payload


def summarize_method(results: list[MethodResult]) -> dict[str, Any]:
    """汇总检索指标。"""

    in_scope = [item for item in results if item.gold_doc_name]
    if not in_scope:
        return {"samples": 0}
    ranks = [item.rank for item in in_scope]
    latencies = [item.elapsed_ms for item in results if item.elapsed_ms > 0]
    return {
        "samples": len(in_scope),
        "recall_at_1": round(sum(1 for rank in ranks if rank == 1) / len(in_scope), 4),
        "recall_at_3": round(sum(1 for rank in ranks if rank is not None and rank <= 3) / len(in_scope), 4),
        "recall_at_5": round(sum(1 for rank in ranks if rank is not None and rank <= 5) / len(in_scope), 4),
        "mrr_at_5": round(sum(1 / rank for rank in ranks if rank is not None and rank <= 5) / len(in_scope), 4),
        "hit_count_at_5": sum(1 for rank in ranks if rank is not None and rank <= 5),
        "top1_hit_count": sum(1 for rank in ranks if rank == 1),
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "p95_latency_ms": percentile(latencies, 0.95) if latencies else 0,
    }


def summarize_by_type(results: list[MethodResult]) -> dict[str, Any]:
    """按问题类型汇总推荐方法效果。"""

    by_type: dict[str, list[MethodResult]] = defaultdict(list)
    for item in results:
        if item.gold_doc_name:
            by_type[item.question_type].append(item)
    return {question_type: summarize_method(items) for question_type, items in sorted(by_type.items())}


def summarize_thresholds(results: list[MethodResult], thresholds: list[float]) -> list[dict[str, Any]]:
    """模拟不同拒答阈值下的接受与拒答效果。"""

    in_scope = [item for item in results if item.gold_doc_name]
    out_scope = [item for item in results if not item.gold_doc_name]
    rows = []
    for threshold in thresholds:
        accepted_in = [item for item in in_scope if (item.top_score or 0.0) >= threshold]
        accepted_out = [item for item in out_scope if (item.top_score or 0.0) >= threshold]
        hit_count = sum(1 for item in accepted_in if item.rank is not None and item.rank <= 5)
        rows.append(
            {
                "threshold": threshold,
                "in_scope_recall_at_5": round(hit_count / len(in_scope), 4) if in_scope else 0.0,
                "in_scope_refusal_rate": round(1 - len(accepted_in) / len(in_scope), 4) if in_scope else 0.0,
                "out_of_scope_refusal_rate": round(1 - len(accepted_out) / len(out_scope), 4) if out_scope else 0.0,
                "accepted_count": len(accepted_in) + len(accepted_out),
            }
        )
    return rows


def summarize_answerability(results: list[MethodResult]) -> dict[str, Any]:
    """评估生成前证据是否足以支撑回答。"""

    in_scope = [item for item in results if item.gold_doc_name]
    if not in_scope:
        return {}
    answerable = [
        item
        for item in in_scope
        if item.rank is not None and item.rank <= 5 and item.context_chars >= 80 and item.citation_ready
    ]
    return {
        "samples": len(in_scope),
        "evidence_answerable_rate": round(len(answerable) / len(in_scope), 4),
        "answerable_count": len(answerable),
        "citation_ready_rate": round(sum(1 for item in in_scope if item.citation_ready) / len(in_scope), 4),
        "avg_context_chars": int(sum(item.context_chars for item in in_scope) / len(in_scope)),
    }


def percentile(values: list[int], ratio: float) -> int:
    """计算简单百分位数。"""

    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def sigmoid(value: float) -> float:
    """把 CrossEncoder 原始分数压缩到 0 到 1。"""

    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


if __name__ == "__main__":
    main()
