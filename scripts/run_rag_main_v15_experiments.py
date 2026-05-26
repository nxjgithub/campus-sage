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

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.utils import utc_now_iso
from app.rag.vector_store import VectorHit
from scripts.run_official_v11_fast_eval import (
    LocalEmbeddingClient,
    build_index_chunks,
    build_rerank_text,
    cosine,
    first_match_rank,
)


DEFAULT_MANIFEST = "docs/examples/official_formal_corpus_v11_manifest.json"
DEFAULT_EVAL_FILE = "docs/examples/eval_set_rag_main_v15.json"
DEFAULT_OUTPUT_DIR = "outputs/eval_rag_main_v15"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"
THRESHOLDS = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


@dataclass(slots=True)
class CaseResult:
    """单题主线实验结果。"""

    item_id: str
    question: str
    question_type: str
    answerable: bool
    gold_doc_name: str | None
    raw_rank_30: int | None
    raw_top_score: float | None
    rerank_rank_by_candidate: dict[str, int | None]
    rerank_top_score_by_candidate: dict[str, float | None]
    top_docs_by_candidate: dict[str, list[str]]
    retrieve_ms: int
    rerank_ms: int


class CachedCrossEncoderReranker:
    """本地 CrossEncoder 重排器，返回 sigmoid 后分数。"""

    def __init__(self, model_name: str, batch_size: int) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name, device="cpu", local_files_only=True)
        self._batch_size = max(1, batch_size)

    def score(self, question: str, hits: list[VectorHit]) -> list[float]:
        """批量计算候选片段相关性分数。"""

        if not hits:
            return []
        pairs = [[question, build_rerank_text(hit)] for hit in hits]
        raw_scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return [sigmoid(float(score)) for score in raw_scores]


def main() -> None:
    """运行 V15 RAG 主线实验并生成论文图表。"""

    parser = argparse.ArgumentParser(description="运行 CampusSage RAG 主线 V15 实验")
    parser.add_argument("--manifest-file", default=DEFAULT_MANIFEST)
    parser.add_argument("--eval-file", default=DEFAULT_EVAL_FILE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", str(ROOT_DIR / "data" / "hf_cache"))
    output_dir = ROOT_DIR / args.output_dir
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(ROOT_DIR / args.manifest_file)
    eval_set = _read_json(ROOT_DIR / args.eval_file)
    items = eval_set.get("items") or []
    embedding = LocalEmbeddingClient(args.embedding_model, args.batch_size)
    reranker = CachedCrossEncoderReranker(args.rerank_model, args.batch_size)

    build_start = time.perf_counter()
    chunks, doc_stats = build_index_chunks(
        manifest=manifest,
        embedding=embedding,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    question_vectors = embedding.embed_texts([str(item["question"]) for item in items])
    build_ms = int((time.perf_counter() - build_start) * 1000)

    cases: list[CaseResult] = []
    for index, (item, query_vector) in enumerate(zip(items, question_vectors, strict=True), start=1):
        question = str(item["question"])
        retrieve_start = time.perf_counter()
        raw_hits = vector_search(chunks, query_vector, 30)
        retrieve_ms = int((time.perf_counter() - retrieve_start) * 1000)

        rerank_start = time.perf_counter()
        scores = reranker.score(question, raw_hits)
        rerank_ms = int((time.perf_counter() - rerank_start) * 1000)
        result = build_case_result(
            item=item,
            raw_hits=raw_hits,
            scores=scores,
            retrieve_ms=retrieve_ms,
            rerank_ms=rerank_ms,
        )
        cases.append(result)
        if index % 10 == 0 or index == len(items):
            print(f"evaluated {index}/{len(items)}", flush=True)

    summary = build_summary(
        eval_set=eval_set,
        manifest=manifest,
        doc_stats=doc_stats,
        chunk_count=len(chunks),
        build_ms=build_ms,
        cases=cases,
        environment={
            "embedding_model": args.embedding_model,
            "rerank_model": args.rerank_model,
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap,
            "batch_size": args.batch_size,
            "candidate_topk_for_topk_curve": 20,
            "recommended_final_topk": 5,
        },
    )
    write_outputs(output_dir, figure_dir, summary)
    print(json.dumps(summary["console"], ensure_ascii=False, indent=2))


def build_case_result(
    *,
    item: dict[str, Any],
    raw_hits: list[VectorHit],
    scores: list[float],
    retrieve_ms: int,
    rerank_ms: int,
) -> CaseResult:
    """根据一次 Top30 召回结果派生不同候选规模的重排结果。"""

    gold_doc_name = item.get("gold_doc_name")
    rank_by_candidate: dict[str, int | None] = {}
    top_score_by_candidate: dict[str, float | None] = {}
    top_docs_by_candidate: dict[str, list[str]] = {}
    for candidate_topk in (5, 10, 20, 30):
        reranked = rerank_subset(raw_hits, scores, candidate_topk)
        key = str(candidate_topk)
        rank_by_candidate[key] = first_match_rank(reranked, gold_doc_name)
        top_score_by_candidate[key] = reranked[0].score if reranked else None
        top_docs_by_candidate[key] = [
            str(hit.payload.get("doc_name") or "") for hit in reranked[:5]
        ]
    return CaseResult(
        item_id=str(item.get("id") or ""),
        question=str(item["question"]),
        question_type=str(item.get("question_type") or "unknown"),
        answerable=bool(item.get("answerable", bool(gold_doc_name))),
        gold_doc_name=gold_doc_name,
        raw_rank_30=first_match_rank(raw_hits, gold_doc_name),
        raw_top_score=raw_hits[0].score if raw_hits else None,
        rerank_rank_by_candidate=rank_by_candidate,
        rerank_top_score_by_candidate=top_score_by_candidate,
        top_docs_by_candidate=top_docs_by_candidate,
        retrieve_ms=retrieve_ms,
        rerank_ms=rerank_ms,
    )


def build_summary(
    *,
    eval_set: dict[str, Any],
    manifest: dict[str, Any],
    doc_stats: list[dict[str, Any]],
    chunk_count: int,
    build_ms: int,
    cases: list[CaseResult],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """汇总 TopK、重排候选规模与阈值实验结果。"""

    in_scope = [case for case in cases if case.gold_doc_name]
    boundary = [case for case in cases if not case.gold_doc_name]
    topk_curve = [
        summarize_topk(in_scope, topk=topk, candidate_key="20")
        for topk in (1, 3, 5, 8)
    ]
    rerank_compare = [
        summarize_raw_vector(in_scope, topk=5),
        summarize_candidate(in_scope, candidate_key="20", topk=5),
    ]
    candidate_curve = [
        summarize_candidate(in_scope, candidate_key=str(candidate), topk=5)
        for candidate in (5, 10, 20, 30)
    ]
    threshold_curve = [
        summarize_threshold(cases, threshold=threshold, candidate_key="20", topk=5)
        for threshold in THRESHOLDS
    ]
    by_type = {
        question_type: summarize_candidate(
            [case for case in in_scope if case.question_type == question_type],
            candidate_key="20",
            topk=5,
        )
        for question_type in sorted({case.question_type for case in in_scope})
    }
    latency_values = [case.retrieve_ms + case.rerank_ms for case in cases]
    payload = {
        "generated_at": utc_now_iso(),
        "eval_set": eval_set.get("name"),
        "source_dir": manifest.get("source_dir"),
        "document_count": manifest.get("document_count"),
        "question_count": len(cases),
        "in_scope_question_count": len(in_scope),
        "boundary_question_count": len(boundary),
        "chunk_count": chunk_count,
        "total_chars": sum(item["char_count"] for item in doc_stats),
        "build_ms": build_ms,
        "environment": environment,
        "topk_curve": topk_curve,
        "rerank_compare": rerank_compare,
        "candidate_curve": candidate_curve,
        "threshold_curve": threshold_curve,
        "type_summary": by_type,
        "latency": {
            "avg_ms": int(sum(latency_values) / len(latency_values)) if latency_values else 0,
            "p95_ms": percentile(latency_values, 0.95),
        },
        "items": [asdict(case) for case in cases],
    }
    payload["console"] = {
        "output_dir": "outputs/eval_rag_main_v15",
        "question_count": payload["question_count"],
        "in_scope_question_count": payload["in_scope_question_count"],
        "boundary_question_count": payload["boundary_question_count"],
        "topk_curve": topk_curve,
        "rerank_compare": rerank_compare,
        "candidate_curve": candidate_curve,
        "threshold_curve": threshold_curve,
        "latency": payload["latency"],
    }
    return payload


def write_outputs(output_dir: Path, figure_dir: Path, summary: dict[str, Any]) -> None:
    """写出 JSON、Markdown 与论文图表。"""

    (output_dir / "rag_main_v15_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_markdown(output_dir / "rag_main_v15_report.md", summary)
    draw_topk_curve(figure_dir / "fig_5_2_topk_curve.png", summary["topk_curve"])
    draw_rerank_compare(figure_dir / "fig_5_3_rerank_ablation.png", summary["rerank_compare"])
    draw_candidate_curve(figure_dir / "fig_5_4_candidate_topk_curve.png", summary["candidate_curve"])
    draw_threshold_curve(figure_dir / "fig_5_5_threshold_curve.png", summary["threshold_curve"])


def vector_search(chunks: list[Any], query_vector: list[float], topk: int) -> list[VectorHit]:
    """执行本地向量检索。"""

    hits = [
        VectorHit(score=cosine(query_vector, chunk.vector), payload=chunk.payload)
        for chunk in chunks
    ]
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:topk]


def rerank_subset(raw_hits: list[VectorHit], scores: list[float], candidate_topk: int) -> list[VectorHit]:
    """对 TopN 候选按 CrossEncoder 分数重排。"""

    scored = [
        VectorHit(score=score, payload=hit.payload)
        for hit, score in zip(raw_hits[:candidate_topk], scores[:candidate_topk], strict=True)
    ]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def summarize_topk(cases: list[CaseResult], *, topk: int, candidate_key: str) -> dict[str, Any]:
    """汇总推荐重排链路在不同 final_topk 下的效果。"""

    ranks = [case.rerank_rank_by_candidate[candidate_key] for case in cases]
    return {
        "topk": topk,
        "samples": len(cases),
        "recall": ratio(sum(1 for rank in ranks if rank is not None and rank <= topk), len(cases)),
        "mrr": mrr(ranks, topk),
        "top1_hit_count": sum(1 for rank in ranks if rank == 1),
        "hit_count": sum(1 for rank in ranks if rank is not None and rank <= topk),
    }


def summarize_raw_vector(cases: list[CaseResult], *, topk: int) -> dict[str, Any]:
    """汇总未重排向量召回结果。"""

    ranks = [case.raw_rank_30 for case in cases]
    return {
        "method": "向量召回",
        "samples": len(cases),
        "topk": topk,
        "recall_at_5": ratio(sum(1 for rank in ranks if rank is not None and rank <= topk), len(cases)),
        "mrr_at_5": mrr(ranks, topk),
        "top1_hit_count": sum(1 for rank in ranks if rank == 1),
        "avg_latency_ms": int(sum(case.retrieve_ms for case in cases) / len(cases)) if cases else 0,
        "p95_latency_ms": percentile([case.retrieve_ms for case in cases], 0.95),
    }


def summarize_candidate(cases: list[CaseResult], *, candidate_key: str, topk: int) -> dict[str, Any]:
    """汇总某个候选规模下的重排结果。"""

    ranks = [case.rerank_rank_by_candidate[candidate_key] for case in cases]
    latency_values = [case.retrieve_ms + case.rerank_ms * int(candidate_key) / 30 for case in cases]
    return {
        "method": f"向量召回+重排 c{candidate_key}",
        "candidate_topk": int(candidate_key),
        "samples": len(cases),
        "topk": topk,
        "recall_at_1": ratio(sum(1 for rank in ranks if rank == 1), len(cases)),
        "recall_at_5": ratio(sum(1 for rank in ranks if rank is not None and rank <= topk), len(cases)),
        "mrr_at_5": mrr(ranks, topk),
        "top1_hit_count": sum(1 for rank in ranks if rank == 1),
        "hit_count_at_5": sum(1 for rank in ranks if rank is not None and rank <= topk),
        "avg_latency_ms": int(sum(latency_values) / len(latency_values)) if latency_values else 0,
        "p95_latency_ms": int(percentile([int(value) for value in latency_values], 0.95)),
    }


def summarize_threshold(
    cases: list[CaseResult],
    *,
    threshold: float,
    candidate_key: str,
    topk: int,
) -> dict[str, Any]:
    """按重排首位分数模拟不同拒答阈值。"""

    in_scope = [case for case in cases if case.gold_doc_name]
    boundary = [case for case in cases if not case.gold_doc_name]

    def accepted(case: CaseResult) -> bool:
        return (case.rerank_top_score_by_candidate[candidate_key] or 0.0) >= threshold

    accepted_in = [case for case in in_scope if accepted(case)]
    accepted_boundary = [case for case in boundary if accepted(case)]
    hits = [
        case
        for case in accepted_in
        if (case.rerank_rank_by_candidate[candidate_key] or 9999) <= topk
    ]
    return {
        "threshold": threshold,
        "in_scope_recall_at_5": ratio(len(hits), len(in_scope)),
        "in_scope_refusal_rate": ratio(len(in_scope) - len(accepted_in), len(in_scope)),
        "boundary_refusal_rate": ratio(len(boundary) - len(accepted_boundary), len(boundary)),
        "accepted_count": len(accepted_in) + len(accepted_boundary),
        "samples": len(cases),
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    """写出论文实验报告。"""

    lines = [
        "# CampusSage RAG 主线 V15 实验报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 评测集：{summary['eval_set']}",
        f"- 文档数：{summary['document_count']}",
        f"- Chunk 数：{summary['chunk_count']}",
        f"- 评测问题数：{summary['question_count']}",
        f"- 知识库内问题：{summary['in_scope_question_count']}",
        f"- 边界/澄清问题：{summary['boundary_question_count']}",
        f"- 平均检索+重排耗时：{summary['latency']['avg_ms']} ms",
        f"- P95 检索+重排耗时：{summary['latency']['p95_ms']} ms",
        "",
        "## TopK 曲线",
        "",
        "| TopK | Recall | MRR | Top1 命中 | 命中数/样本 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["topk_curve"]:
        lines.append(
            f"| {row['topk']} | {row['recall']:.4f} | {row['mrr']:.4f} | "
            f"{row['top1_hit_count']} | {row['hit_count']}/{row['samples']} |"
        )
    lines.extend(
        [
            "",
            "## 重排消融",
            "",
            "| 方法 | Recall@5 | MRR@5 | Top1 命中 | 平均耗时(ms) | P95耗时(ms) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["rerank_compare"]:
        lines.append(
            f"| {row['method']} | {row['recall_at_5']:.4f} | {row['mrr_at_5']:.4f} | "
            f"{row['top1_hit_count']} | {row['avg_latency_ms']} | {row['p95_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            "## Candidate TopK 曲线",
            "",
            "| candidate_topk | Recall@1 | Recall@5 | MRR@5 | 折算平均耗时(ms) | 折算P95耗时(ms) |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["candidate_curve"]:
        lines.append(
            f"| {row['candidate_topk']} | {row['recall_at_1']:.4f} | {row['recall_at_5']:.4f} | "
            f"{row['mrr_at_5']:.4f} | {row['avg_latency_ms']} | {row['p95_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            "## 拒答阈值曲线",
            "",
            "| threshold | 知识库内 Recall@5 | 知识库内误拒率 | 边界问题拒答率 | 接受数 |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["threshold_curve"]:
        lines.append(
            f"| {row['threshold']:.2f} | {row['in_scope_recall_at_5']:.4f} | "
            f"{row['in_scope_refusal_rate']:.4f} | {row['boundary_refusal_rate']:.4f} | "
            f"{row['accepted_count']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def draw_topk_curve(path: Path, rows: list[dict[str, Any]]) -> None:
    """绘制 TopK 对召回质量影响图。"""

    chart = ChartCanvas(
        title="TopK 对证据召回质量的影响",
        subtitle="V15 评测集，向量召回 + Cross-Encoder 重排，candidate_topk=20",
    )
    xs = [str(row["topk"]) for row in rows]
    chart.draw_line_chart(
        path=path,
        x_labels=xs,
        series=[
            ("Recall@K", [row["recall"] for row in rows], "#2563EB"),
            ("MRR@K", [row["mrr"] for row in rows], "#059669"),
        ],
        y_min=0.93,
        y_max=0.99,
        x_axis_title="最终返回 TopK",
        y_axis_title="指标值",
    )


def draw_rerank_compare(path: Path, rows: list[dict[str, Any]]) -> None:
    """绘制重排消融柱状图。"""

    chart = ChartCanvas(
        title="重排消融实验",
        subtitle="比较向量召回与向量召回 + 重排在 Top5 证据上的表现",
    )
    chart.draw_grouped_bar_chart(
        path=path,
        x_labels=[row["method"] for row in rows],
        series=[
            ("Recall@5", [row["recall_at_5"] for row in rows], "#2563EB"),
            ("MRR@5", [row["mrr_at_5"] for row in rows], "#059669"),
            ("Top1命中率", [row["top1_hit_count"] / row["samples"] for row in rows], "#D97706"),
        ],
        y_min=0,
        y_max=1,
        x_axis_title="方法",
        y_axis_title="指标值",
    )


def draw_candidate_curve(path: Path, rows: list[dict[str, Any]]) -> None:
    """绘制候选规模收益与成本图。"""

    chart = ChartCanvas(
        title="候选证据规模对重排收益与耗时的影响",
        subtitle="final_topk=5；左轴为质量指标，右轴为平均耗时线性折算值",
    )
    x_labels = [str(row["candidate_topk"]) for row in rows]
    chart.draw_dual_axis_line_chart(
        path=path,
        x_labels=x_labels,
        left_series=[
            ("Recall@5", [row["recall_at_5"] for row in rows], "#2563EB"),
            ("MRR@5", [row["mrr_at_5"] for row in rows], "#059669"),
        ],
        right_series=("折算耗时(ms)", [row["avg_latency_ms"] for row in rows], "#DC2626"),
        left_min=0.90,
        left_max=1.00,
        x_axis_title="重排候选规模 candidate_topk",
        left_axis_title="指标值",
        right_axis_title="耗时(ms)",
    )


def draw_threshold_curve(path: Path, rows: list[dict[str, Any]]) -> None:
    """绘制拒答阈值曲线。"""

    chart = ChartCanvas(
        title="拒答阈值对回答边界的影响",
        subtitle="阈值越高系统越保守，需要平衡库外拒答率与库内误拒率",
    )
    x_labels = [f"{row['threshold']:.2f}" for row in rows]
    chart.draw_line_chart(
        path=path,
        x_labels=x_labels,
        series=[
            ("边界问题拒答率", [row["boundary_refusal_rate"] for row in rows], "#2563EB"),
            ("知识库内误拒率", [row["in_scope_refusal_rate"] for row in rows], "#DC2626"),
            ("知识库内Recall@5", [row["in_scope_recall_at_5"] for row in rows], "#059669"),
        ],
        y_min=0,
        y_max=1,
        x_axis_title="拒答阈值 threshold",
        y_axis_title="比例",
    )


class ChartCanvas:
    """基于 PIL 的论文图表绘制器，避免新增绘图库依赖。"""

    def __init__(self, *, title: str, subtitle: str) -> None:
        self.title = title
        self.subtitle = subtitle
        self.width = 1800
        self.height = 1200
        self.margin_left = 190
        self.margin_right = 150
        self.margin_top = 190
        self.margin_bottom = 190
        self.bg = "#FFFFFF"
        self.fg = "#111827"
        self.muted = "#6B7280"
        self.grid = "#E5E7EB"
        self.axis = "#9CA3AF"
        self.font_title = load_font(54, bold=True)
        self.font_subtitle = load_font(28)
        self.font_axis = load_font(28)
        self.font_tick = load_font(24)
        self.font_legend = load_font(26)

    def draw_line_chart(
        self,
        *,
        path: Path,
        x_labels: list[str],
        series: list[tuple[str, list[float], str]],
        y_min: float,
        y_max: float,
        x_axis_title: str,
        y_axis_title: str,
        annotate: bool = True,
    ) -> None:
        """绘制单轴折线图。"""

        image, draw = self._base()
        plot = self._plot_area()
        self._draw_axes(draw, plot, x_labels, y_min, y_max, x_axis_title, y_axis_title)
        for series_index, (name, values, color) in enumerate(series):
            points = self._points(plot, values, y_min, y_max)
            self._draw_line(draw, points, color)
            if not annotate:
                for point in points:
                    self._draw_marker(draw, point, color)
                continue
            for point, value in zip(points, values, strict=True):
                self._draw_marker(draw, point, color)
                offset_y = -46 - series_index * 32
                if series_index >= 2:
                    offset_y = 28 + (series_index - 2) * 32
                if point[1] + offset_y < plot[1] - 4:
                    offset_y = 28 + series_index * 30
                if point[1] + offset_y > plot[3] - 24:
                    offset_y = -46 - series_index * 30
                draw.text((point[0] - 32, point[1] + offset_y), f"{value:.3f}", fill=color, font=self.font_tick)
        self._draw_legend(draw, series=[(name, color) for name, _, color in series])
        image.save(path)

    def draw_grouped_bar_chart(
        self,
        *,
        path: Path,
        x_labels: list[str],
        series: list[tuple[str, list[float], str]],
        y_min: float,
        y_max: float,
        x_axis_title: str,
        y_axis_title: str,
    ) -> None:
        """绘制分组柱状图。"""

        image, draw = self._base()
        plot = self._plot_area()
        self._draw_axes(draw, plot, x_labels, y_min, y_max, x_axis_title, y_axis_title, categorical=True)
        group_width = plot[2] - plot[0]
        step = group_width / max(1, len(x_labels))
        bar_width = min(80, step / (len(series) + 1.4))
        for group_index, _ in enumerate(x_labels):
            center = plot[0] + step * group_index + step / 2
            start_x = center - (bar_width * len(series)) / 2
            for series_index, (_, values, color) in enumerate(series):
                value = values[group_index]
                x0 = start_x + series_index * bar_width
                x1 = x0 + bar_width * 0.78
                y = self._y(plot, value, y_min, y_max)
                draw.rounded_rectangle((x0, y, x1, plot[3]), radius=8, fill=color)
                draw.text((x0 - 8, y - 38), f"{value:.3f}", fill=color, font=self.font_tick)
        self._draw_legend(draw, series=[(name, color) for name, _, color in series])
        image.save(path)

    def draw_dual_axis_line_chart(
        self,
        *,
        path: Path,
        x_labels: list[str],
        left_series: list[tuple[str, list[float], str]],
        right_series: tuple[str, list[float], str],
        left_min: float,
        left_max: float,
        x_axis_title: str,
        left_axis_title: str,
        right_axis_title: str,
    ) -> None:
        """绘制双轴折线图。"""

        image, draw = self._base()
        plot = self._plot_area()
        self._draw_axes(draw, plot, x_labels, left_min, left_max, x_axis_title, left_axis_title)
        right_name, right_values, right_color = right_series
        right_max = nice_upper(max(right_values) if right_values else 1)
        for tick in range(0, 6):
            value = right_max * tick / 5
            y = plot[3] - (plot[3] - plot[1]) * tick / 5
            draw.text((plot[2] + 18, y - 13), str(int(value)), fill=self.muted, font=self.font_tick)
        draw.text((plot[2] - 20, plot[1] - 60), right_axis_title, fill=self.muted, font=self.font_axis)
        for series_index, (name, values, color) in enumerate(left_series):
            points = self._points(plot, values, left_min, left_max)
            self._draw_line(draw, points, color)
            for point, value in zip(points, values, strict=True):
                self._draw_marker(draw, point, color)
                offset_y = -46 - series_index * 32
                if point[1] + offset_y < plot[1] - 4:
                    offset_y = 28 + series_index * 30
                if point[1] + offset_y > plot[3] - 24:
                    offset_y = -46 - series_index * 30
                draw.text(
                    (point[0] - 32, point[1] + offset_y),
                    f"{value:.3f}",
                    fill=color,
                    font=self.font_tick,
                )
        right_points = self._points(plot, right_values, 0, right_max)
        self._draw_line(draw, right_points, right_color)
        for point, value in zip(right_points, right_values, strict=True):
            self._draw_marker(draw, point, right_color)
            draw.text((point[0] - 34, point[1] - 44), str(int(value)), fill=right_color, font=self.font_tick)
        legend = [(name, color) for name, _, color in left_series]
        legend.append((right_name, right_color))
        self._draw_legend(draw, series=legend)
        image.save(path)

    def _base(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """创建画布并绘制标题。"""

        image = Image.new("RGB", (self.width, self.height), self.bg)
        draw = ImageDraw.Draw(image)
        return image, draw

    def _plot_area(self) -> tuple[int, int, int, int]:
        """返回绘图区坐标。"""

        return (
            self.margin_left,
            self.margin_top,
            self.width - self.margin_right,
            self.height - self.margin_bottom,
        )

    def _draw_axes(
        self,
        draw: ImageDraw.ImageDraw,
        plot: tuple[int, int, int, int],
        x_labels: list[str],
        y_min: float,
        y_max: float,
        x_axis_title: str,
        y_axis_title: str,
        categorical: bool = False,
    ) -> None:
        """绘制坐标轴、网格与刻度。"""

        left, top, right, bottom = plot
        for tick in range(0, 6):
            value = y_min + (y_max - y_min) * tick / 5
            y = bottom - (bottom - top) * tick / 5
            draw.line((left, y, right, y), fill=self.grid, width=2)
            draw.text((58, y - 15), format_tick(value, y_max - y_min), fill=self.muted, font=self.font_tick)
        draw.line((left, top, left, bottom), fill=self.axis, width=3)
        draw.line((left, bottom, right, bottom), fill=self.axis, width=3)
        if categorical:
            step = (right - left) / max(1, len(x_labels))
        else:
            step = (right - left) / max(1, len(x_labels) - 1)
            if len(x_labels) == 1:
                step = 0
        for index, label in enumerate(x_labels):
            if categorical:
                x = left + step * index + step / 2
            else:
                x = left + step * index if len(x_labels) > 1 else (left + right) / 2
            draw.line((x, bottom, x, bottom + 10), fill=self.axis, width=2)
            text_width = draw.textlength(label, font=self.font_tick)
            draw.text((x - text_width / 2, bottom + 24), label, fill=self.muted, font=self.font_tick)
        title_width = draw.textlength(x_axis_title, font=self.font_axis)
        draw.text((right - title_width, bottom + 82), x_axis_title, fill=self.fg, font=self.font_axis)
        draw.text((left, top - 52), y_axis_title, fill=self.fg, font=self.font_axis)

    def _points(
        self,
        plot: tuple[int, int, int, int],
        values: list[float],
        y_min: float,
        y_max: float,
    ) -> list[tuple[float, float]]:
        """把数值转换为绘图区坐标。"""

        left, _, right, _ = plot
        if len(values) == 1:
            xs = [(left + right) / 2]
        else:
            step = (right - left) / (len(values) - 1)
            xs = [left + step * index for index in range(len(values))]
        return [(x, self._y(plot, value, y_min, y_max)) for x, value in zip(xs, values, strict=True)]

    def _y(
        self,
        plot: tuple[int, int, int, int],
        value: float,
        y_min: float,
        y_max: float,
    ) -> float:
        """计算 y 坐标。"""

        _, top, _, bottom = plot
        ratio_value = (value - y_min) / max(0.0001, y_max - y_min)
        ratio_value = max(0.0, min(1.0, ratio_value))
        return bottom - (bottom - top) * ratio_value

    def _draw_line(
        self,
        draw: ImageDraw.ImageDraw,
        points: list[tuple[float, float]],
        color: str,
    ) -> None:
        """绘制折线。"""

        if len(points) >= 2:
            draw.line(points, fill=color, width=7, joint="curve")

    def _draw_marker(
        self,
        draw: ImageDraw.ImageDraw,
        point: tuple[float, float],
        color: str,
    ) -> None:
        """绘制圆点标记。"""

        x, y = point
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill="#FFFFFF", outline=color, width=6)

    def _draw_legend(self, draw: ImageDraw.ImageDraw, *, series: list[tuple[str, str]]) -> None:
        """绘制图例。"""

        item_widths = [
            int(draw.textlength(name, font=self.font_legend)) + 122
            for name, _ in series
        ]
        x = self.width - self.margin_right - sum(item_widths)
        y = 58
        for name, color in series:
            draw.rounded_rectangle((x, y, x + 44, y + 18), radius=6, fill=color)
            draw.text((x + 58, y - 6), name, fill=self.fg, font=self.font_legend)
            x += int(draw.textlength(name, font=self.font_legend)) + 122


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载中文字体，保证图表在 Windows 环境中可读。"""

    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def format_tick(value: float, span: float) -> str:
    """根据坐标范围选择刻度小数位。"""

    if span <= 0.2:
        return f"{value:.2f}"
    return f"{value:.1f}"


def _read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON。"""

    return json.loads(path.read_text(encoding="utf-8"))


def ratio(numerator: int, denominator: int) -> float:
    """计算四位小数比例。"""

    return round(numerator / denominator, 4) if denominator else 0.0


def mrr(ranks: list[int | None], topk: int) -> float:
    """计算 MRR@K。"""

    if not ranks:
        return 0.0
    return round(
        sum(1 / rank for rank in ranks if rank is not None and rank <= topk) / len(ranks),
        4,
    )


def percentile(values: list[int], ratio_value: float) -> int:
    """计算简单百分位值。"""

    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio_value) - 1))
    return ordered[index]


def sigmoid(value: float) -> float:
    """把 CrossEncoder 原始分数压缩到 0 到 1。"""

    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def nice_upper(value: float) -> float:
    """为右轴生成美观上界。"""

    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    if normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


if __name__ == "__main__":
    main()
