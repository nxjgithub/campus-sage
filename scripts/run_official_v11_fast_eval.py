from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid5, UUID

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.settings import get_settings
from app.core.utils import utc_now_iso
from app.ingest.chunker import Chunker
from app.ingest.parser import DocumentParser
from app.rag.embedding import HttpEmbeddingClient
from app.rag.reranker import get_reranker
from app.rag.vector_store import VectorHit


POINT_NAMESPACE = UUID("57f77fb8-1ab8-41bb-b4f7-438f68f71f89")


@dataclass(slots=True)
class IndexedChunk:
    """离线评测中的单个向量片段。"""

    vector: list[float]
    payload: dict[str, Any]


@dataclass(slots=True)
class EvalItemResult:
    """单题检索评测结果。"""

    question: str
    gold_doc_name: str | None
    raw_rank: int | None
    rerank_rank: int | None
    raw_top_score: float | None
    rerank_top_score: float | None
    elapsed_ms: int
    raw_top_docs: list[str]
    rerank_top_docs: list[str]


class LocalEmbeddingClient:
    """使用本地 sentence-transformers 模型生成向量。"""

    def __init__(self, model_name: str, batch_size: int) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            model_name,
            device="cpu",
            local_files_only=True,
        )
        self._batch_size = max(1, batch_size)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量。"""

        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]


class LocalReranker:
    """使用本地 CrossEncoder 执行重排。"""

    def __init__(self, model_name: str, batch_size: int) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(
            model_name,
            device="cpu",
            local_files_only=True,
        )
        self._batch_size = max(1, batch_size)

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """按 CrossEncoder 分数重排候选片段。"""

        if not hits:
            return hits
        pairs = [[question, build_rerank_text(hit)] for hit in hits]
        scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        indexed = list(enumerate(hits))
        return [
            hit
            for index, hit in sorted(
                indexed,
                key=lambda item: (float(scores[item[0]]), item[1].score),
                reverse=True,
            )
        ]


def build_rerank_text(hit: VectorHit) -> str:
    """将候选片段组装为重排输入文本。"""

    payload = hit.payload
    parts = [
        str(payload.get("doc_name") or "").strip(),
        str(payload.get("section_path") or "").strip(),
        str(payload.get("text") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def main() -> None:
    """运行 V11 正式文件快速实验。"""

    parser = argparse.ArgumentParser(description="运行 V11 正式文件快速检索重排实验")
    parser.add_argument("--manifest-file", default="docs/examples/official_formal_corpus_v11_manifest.json")
    parser.add_argument("--eval-file", default="docs/examples/eval_set_official_formal_v11.json")
    parser.add_argument("--output-dir", default="outputs/eval_official_formal_v11_fast")
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--embedding-api-path", default="/v1/embeddings")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--embedding-backend", choices=("local", "http"), default="local")
    parser.add_argument("--embedding-batch-size", type=int, default=2)
    parser.add_argument("--rerank-backend", choices=("local", "http"), default="local")
    parser.add_argument("--rerank-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--candidate-topk", type=int, default=20)
    args = parser.parse_args()

    output_dir = ROOT_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(ROOT_DIR / "data" / "hf_cache"))
    if args.embedding_backend == "http":
        settings = get_settings().model_copy(
            update={
                "embedding_backend": "http",
                "embedding_base_url": args.embedding_base_url,
                "embedding_api_path": args.embedding_api_path,
                "embedding_model_name": args.embedding_model,
                "embedding_batch_size": max(1, args.embedding_batch_size),
            }
        )
        embedding = HttpEmbeddingClient(settings)
    else:
        embedding = LocalEmbeddingClient(args.embedding_model, args.embedding_batch_size)
    if args.rerank_backend == "http":
        reranker = get_reranker(get_settings())
        reranker_name = f"{get_settings().rerank_backend}:{get_settings().rerank_model_name}"
    else:
        reranker = LocalReranker(args.rerank_model, args.embedding_batch_size)
        reranker_name = f"local:{args.rerank_model}"
    manifest = json.loads((ROOT_DIR / args.manifest_file).read_text(encoding="utf-8"))
    eval_set = json.loads((ROOT_DIR / args.eval_file).read_text(encoding="utf-8"))

    start = time.perf_counter()
    chunks, doc_stats = build_index_chunks(
        manifest=manifest,
        embedding=embedding,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    ingest_ms = int((time.perf_counter() - start) * 1000)
    questions = eval_set.get("items") or []
    query_vectors = embedding.embed_texts([str(item["question"]) for item in questions])

    item_results: list[EvalItemResult] = []
    for index, (item, query_vector) in enumerate(zip(questions, query_vectors, strict=True), start=1):
        case_start = time.perf_counter()
        raw_hits = search(chunks, query_vector, args.candidate_topk)
        reranked_hits = reranker.rerank(str(item["question"]), raw_hits)
        elapsed_ms = int((time.perf_counter() - case_start) * 1000)
        gold_doc_name = item.get("gold_doc_name")
        result = EvalItemResult(
            question=str(item["question"]),
            gold_doc_name=gold_doc_name,
            raw_rank=first_match_rank(raw_hits, gold_doc_name),
            rerank_rank=first_match_rank(reranked_hits, gold_doc_name),
            raw_top_score=raw_hits[0].score if raw_hits else None,
            rerank_top_score=reranked_hits[0].score if reranked_hits else None,
            elapsed_ms=elapsed_ms,
            raw_top_docs=top_doc_names(raw_hits, 5),
            rerank_top_docs=top_doc_names(reranked_hits, 5),
        )
        item_results.append(result)
        if index % 10 == 0 or index == len(questions):
            print(f"evaluated {index}/{len(questions)}", flush=True)

    payload = build_summary(
        manifest=manifest,
        eval_set=eval_set,
        doc_stats=doc_stats,
        item_results=item_results,
        chunk_count=len(chunks),
        ingest_ms=ingest_ms,
        environment={
            "embedding_backend": args.embedding_backend,
            "embedding_model": args.embedding_model,
            "embedding_base_url": args.embedding_base_url,
            "embedding_batch_size": args.embedding_batch_size,
            "reranker": reranker_name,
            "candidate_topk": args.candidate_topk,
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap,
        },
    )
    (output_dir / "official_v11_fast_eval_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(output_dir / "official_v11_fast_eval_report.md", payload)
    print(json.dumps(payload["console"], ensure_ascii=False, indent=2))


def build_index_chunks(
    *,
    manifest: dict[str, Any],
    embedding: HttpEmbeddingClient,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[IndexedChunk], list[dict[str, Any]]]:
    """解析正式文件、分块、向量化，并构建本地检索索引。"""

    parser = DocumentParser()
    chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_texts: list[str] = []
    payloads: list[dict[str, Any]] = []
    doc_stats: list[dict[str, Any]] = []
    for doc_index, document in enumerate(manifest.get("documents") or [], start=1):
        source_path = ROOT_DIR / str(document["source_path"])
        pages = parser.parse(source_path)
        chunks = chunker.build(pages)
        doc_id = f"doc_{uuid5(POINT_NAMESPACE, source_path.name).hex}"
        for chunk in chunks:
            chunk_id = f"official_v11_{doc_index}_{chunk.chunk_index}"
            payload = {
                "kb_id": "official_v11_fast",
                "doc_id": doc_id,
                "doc_name": source_path.name,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_path": chunk.section_path,
                "chunk_id": chunk_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "source_uri": str(source_path.relative_to(ROOT_DIR)),
            }
            payloads.append(payload)
            all_texts.append(chunk.text)
        doc_stats.append(
            {
                "doc_name": source_path.name,
                "parsed_units": len(pages),
                "chunk_count": len(chunks),
                "char_count": sum(len(page.text) for page in pages),
            }
        )
    vectors = embedding.embed_texts(all_texts)
    return [
        IndexedChunk(vector=vector, payload=payload)
        for vector, payload in zip(vectors, payloads, strict=True)
    ], doc_stats


def search(chunks: list[IndexedChunk], query_vector: list[float], topk: int) -> list[VectorHit]:
    """使用余弦相似度执行本地 TopK 检索。"""

    hits = [
        VectorHit(score=cosine(query_vector, chunk.vector), payload=chunk.payload)
        for chunk in chunks
    ]
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:topk]


def cosine(left: list[float], right: list[float]) -> float:
    """计算余弦相似度。"""

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


def first_match_rank(hits: list[VectorHit], gold_doc_name: str | None) -> int | None:
    """返回标准文档首次出现的排名。"""

    if not gold_doc_name:
        return None
    for index, hit in enumerate(hits, start=1):
        if hit.payload.get("doc_name") == gold_doc_name:
            return index
    return None


def top_doc_names(hits: list[VectorHit], topk: int) -> list[str]:
    """提取前若干候选的文档名。"""

    return [str(hit.payload.get("doc_name") or "") for hit in hits[:topk]]


def build_summary(
    *,
    manifest: dict[str, Any],
    eval_set: dict[str, Any],
    doc_stats: list[dict[str, Any]],
    item_results: list[EvalItemResult],
    chunk_count: int,
    ingest_ms: int,
    environment: dict[str, Any],
) -> dict[str, Any]:
    """汇总正式文件实验指标。"""

    in_scope = [item for item in item_results if item.gold_doc_name]
    out_scope = [item for item in item_results if not item.gold_doc_name]
    topk_results = [
        summarize_topk(in_scope, topk=3, rank_attr="rerank_rank"),
        summarize_topk(in_scope, topk=5, rank_attr="rerank_rank"),
        summarize_topk(in_scope, topk=8, rank_attr="rerank_rank"),
    ]
    raw_result = summarize_topk(in_scope, topk=5, rank_attr="raw_rank")
    rerank_result = summarize_topk(in_scope, topk=5, rank_attr="rerank_rank")
    threshold_results = [
        summarize_threshold(item_results, threshold=None),
        summarize_threshold(item_results, threshold=0.25),
        summarize_threshold(item_results, threshold=0.50),
    ]
    latency_values = [item.elapsed_ms for item in item_results]
    payload = {
        "generated_at": utc_now_iso(),
        "eval_set": eval_set.get("name"),
        "source_dir": manifest.get("source_dir"),
        "document_count": manifest.get("document_count"),
        "skipped_count": manifest.get("skipped_count"),
        "question_count": len(item_results),
        "in_scope_question_count": len(in_scope),
        "out_of_scope_question_count": len(out_scope),
        "chunk_count": chunk_count,
        "total_chars": sum(item["char_count"] for item in doc_stats),
        "ingest_ms": ingest_ms,
        "environment": environment,
        "topk_results": topk_results,
        "rerank_compare": [
            {"rerank_enabled": False, **raw_result},
            {"rerank_enabled": True, **rerank_result},
        ],
        "threshold_results": threshold_results,
        "latency": {
            "avg_ms": int(sum(latency_values) / len(latency_values)) if latency_values else 0,
            "p95_ms": percentile(latency_values, 0.95),
        },
        "documents": doc_stats,
        "items": [asdict(item) for item in item_results],
    }
    payload["console"] = {
        "document_count": payload["document_count"],
        "question_count": payload["question_count"],
        "chunk_count": payload["chunk_count"],
        "topk_results": topk_results,
        "rerank_compare": payload["rerank_compare"],
        "threshold_results": threshold_results,
        "latency": payload["latency"],
    }
    return payload


def summarize_topk(
    items: list[EvalItemResult],
    *,
    topk: int,
    rank_attr: str,
) -> dict[str, Any]:
    """汇总 Recall@K、MRR 与 Top1 命中。"""

    ranks = [getattr(item, rank_attr) for item in items]
    hits = [rank for rank in ranks if rank is not None and rank <= topk]
    reciprocal = [1 / rank for rank in hits]
    return {
        "topk": topk,
        "recall": round(len(hits) / len(items), 4) if items else 0.0,
        "mrr": round(sum(reciprocal) / len(items), 4) if items else 0.0,
        "top1_hit_count": sum(1 for rank in ranks if rank == 1),
        "hit_count": len(hits),
        "samples": len(items),
    }


def summarize_threshold(
    items: list[EvalItemResult],
    *,
    threshold: float | None,
) -> dict[str, Any]:
    """按重排后首位分数模拟阈值拒答结果。"""

    in_scope = [item for item in items if item.gold_doc_name]
    out_scope = [item for item in items if not item.gold_doc_name]

    def accepted(item: EvalItemResult) -> bool:
        if threshold is None:
            return True
        return (item.rerank_top_score or 0.0) >= threshold

    accepted_in_scope = [item for item in in_scope if accepted(item)]
    accepted_out_scope = [item for item in out_scope if accepted(item)]
    hit_count = sum(
        1
        for item in accepted_in_scope
        if item.rerank_rank is not None and item.rerank_rank <= 5
    )
    return {
        "threshold": threshold,
        "in_scope_recall_at_5": round(hit_count / len(in_scope), 4) if in_scope else 0.0,
        "in_scope_refusal_rate": round(1 - len(accepted_in_scope) / len(in_scope), 4) if in_scope else 0.0,
        "out_of_scope_refusal_rate": round(1 - len(accepted_out_scope) / len(out_scope), 4) if out_scope else 0.0,
        "accepted_count": len(accepted_in_scope) + len(accepted_out_scope),
        "samples": len(items),
    }


def percentile(values: list[int], ratio: float) -> int:
    """计算简单百分位值。"""

    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(math.ceil(len(ordered) * ratio) - 1)))
    return ordered[index]


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    """写出论文可引用的实验报告。"""

    lines = [
        "# CampusSage V11 正式文件扩展实验报告",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 原始目录：{payload['source_dir']}",
        f"- 可解析文档数：{payload['document_count']}",
        f"- 评测问题数：{payload['question_count']}",
        f"- 文本块数：{payload['chunk_count']}",
        f"- 总字符数：{payload['total_chars']}",
        f"- 平均耗时：{payload['latency']['avg_ms']} ms",
        f"- P95 耗时：{payload['latency']['p95_ms']} ms",
        "",
        "## TopK 结果",
        "",
        "| TopK | Recall | MRR | Top1命中 | 命中数/样本 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["topk_results"]:
        lines.append(
            f"| {item['topk']} | {item['recall']} | {item['mrr']} | "
            f"{item['top1_hit_count']} | {item['hit_count']}/{item['samples']} |"
        )
    lines.extend(["", "## 重排对比", "", "| rerank | Recall@5 | MRR | Top1命中 |", "| --- | --- | --- | --- |"])
    for item in payload["rerank_compare"]:
        lines.append(
            f"| {item['rerank_enabled']} | {item['recall']} | {item['mrr']} | {item['top1_hit_count']} |"
        )
    lines.extend(["", "## 阈值对比", "", "| threshold | 知识库内Recall@5 | 知识库内拒答率 | 知识库外拒答率 |", "| --- | --- | --- | --- |"])
    for item in payload["threshold_results"]:
        threshold = "none" if item["threshold"] is None else item["threshold"]
        lines.append(
            f"| {threshold} | {item['in_scope_recall_at_5']} | "
            f"{item['in_scope_refusal_rate']} | {item['out_of_scope_refusal_rate']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
