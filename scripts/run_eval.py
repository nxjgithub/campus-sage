from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import get_settings
from app.eval.dto import EvalItem, EvalItemResult, EvalResult, EvalSet
from app.eval.runner import run_eval_with_details


@dataclass(frozen=True, slots=True)
class EvalExperimentConfig:
    """描述一组待比较的评测参数。"""

    name: str
    topk: int
    threshold: float | None
    rerank_enabled: bool


def main() -> None:
    """评测脚本入口。"""

    parser = argparse.ArgumentParser(description="运行 CampusSage 评测")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument("--eval-file", required=True, help="评测集 JSON 文件路径")
    parser.add_argument("--topk", type=int, default=5, help="单次评测的检索 TopK")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="单次评测的分数阈值，不传则不额外过滤",
    )
    parser.add_argument(
        "--rerank-enabled",
        action="store_true",
        help="单次评测是否启用重排",
    )
    parser.add_argument(
        "--compare-topk",
        default=None,
        help="逗号分隔的 TopK 列表，用于批量参数对比，例如 3,5,8",
    )
    parser.add_argument(
        "--compare-threshold",
        default=None,
        help="逗号分隔的 threshold 列表，使用 none 表示不设阈值",
    )
    parser.add_argument(
        "--compare-rerank",
        default=None,
        help="逗号分隔的 rerank 开关列表，例如 false,true",
    )
    parser.add_argument(
        "--embedding-backend",
        choices=("http", "simple", "local"),
        default=None,
        help="覆盖当前评测脚本使用的 Embedding 后端",
    )
    parser.add_argument(
        "--embedding-base-url",
        default=None,
        help="覆盖当前评测脚本使用的 Embedding 服务地址",
    )
    parser.add_argument(
        "--embedding-api-path",
        default=None,
        help="覆盖当前评测脚本使用的 Embedding 接口路径",
    )
    parser.add_argument(
        "--vector-backend",
        choices=("memory", "qdrant"),
        default=None,
        help="覆盖当前评测脚本使用的向量后端",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="覆盖当前评测脚本使用的 Qdrant 地址",
    )
    parser.add_argument(
        "--show-items",
        action="store_true",
        help="输出逐题评测明细，便于定位阈值与排序问题",
    )
    args = parser.parse_args()

    try:
        experiment_configs = build_experiment_configs(
            topk=args.topk,
            threshold=args.threshold,
            rerank_enabled=args.rerank_enabled,
            compare_topk=args.compare_topk,
            compare_threshold=args.compare_threshold,
            compare_rerank=args.compare_rerank,
        )
    except ValueError as exc:
        parser.error(str(exc))

    eval_set = load_eval_set(Path(args.eval_file))
    settings = build_effective_settings(
        base_settings=get_settings(),
        embedding_backend=args.embedding_backend,
        embedding_base_url=args.embedding_base_url,
        embedding_api_path=args.embedding_api_path,
        vector_backend=args.vector_backend,
        qdrant_url=args.qdrant_url,
    )
    try:
        experiment_results = run_experiments(
            kb_id=args.kb_id,
            eval_set=eval_set,
            configs=experiment_configs,
            settings=settings,
        )
    except AppError as exc:
        raise SystemExit(format_eval_runtime_error(exc, settings)) from exc

    if len(experiment_results) == 1:
        output = _single_result_payload(
            eval_set_name=eval_set.name,
            kb_id=args.kb_id,
            config=experiment_results[0].config,
            result=experiment_results[0].result,
            items=experiment_results[0].item_results if args.show_items else None,
        )
    else:
        output = _compare_result_payload(
            eval_set_name=eval_set.name,
            kb_id=args.kb_id,
            experiments=experiment_results,
            show_items=args.show_items,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


@dataclass(frozen=True, slots=True)
class EvalExperimentResult:
    """承载单组实验配置及其评测结果。"""

    config: EvalExperimentConfig
    result: EvalResult
    item_results: list[EvalItemResult]


def build_effective_settings(
    *,
    base_settings,
    embedding_backend: str | None,
    embedding_base_url: str | None,
    embedding_api_path: str | None,
    vector_backend: str | None,
    qdrant_url: str | None,
):
    """基于命令行参数生成当前评测使用的配置副本。"""

    overrides: dict[str, object] = {}
    if embedding_backend is not None:
        overrides["embedding_backend"] = embedding_backend
    if embedding_base_url is not None:
        overrides["embedding_base_url"] = embedding_base_url
    if embedding_api_path is not None:
        overrides["embedding_api_path"] = embedding_api_path
    if vector_backend is not None:
        overrides["vector_backend"] = vector_backend
    if qdrant_url is not None:
        overrides["qdrant_url"] = qdrant_url
    if not overrides:
        return base_settings
    return base_settings.model_copy(update=overrides)


def format_eval_runtime_error(error: AppError, settings) -> str:
    """生成更适合命令行排障的中文错误提示。"""

    lines = [f"评测执行失败：{error}"]
    if error.code == ErrorCode.EMBEDDING_FAILED:
        lines.append(
            f"当前 Embedding 配置：backend={settings.embedding_backend}, "
            f"base_url={settings.embedding_base_url}, api_path={settings.embedding_api_path}"
        )
        if settings.embedding_backend == "http":
            lines.append("排查建议：")
            lines.append("1. 确认 Embedding 服务已启动且地址可达。")
            lines.append(
                "2. 若本地 API 是用 simple/local embedding 跑通的，"
                "请给 run_eval.py 传入相同覆盖参数。"
            )
            lines.append(
                "3. 例如：--embedding-backend simple，或补充 "
                "--embedding-base-url 与 --embedding-api-path。"
            )
    elif error.code == ErrorCode.VECTOR_SEARCH_FAILED:
        lines.append(
            f"当前向量检索配置：backend={settings.vector_backend}, qdrant_url={settings.qdrant_url}"
        )
        if settings.vector_backend == "qdrant":
            lines.append("排查建议：确认 Qdrant 已启动，且知识库数据已成功写入该实例。")
    return "\n".join(lines)


def build_experiment_configs(
    *,
    topk: int,
    threshold: float | None,
    rerank_enabled: bool,
    compare_topk: str | None,
    compare_threshold: str | None,
    compare_rerank: str | None,
) -> list[EvalExperimentConfig]:
    """构建单次运行或参数矩阵实验配置。"""

    if not any(value is not None for value in (compare_topk, compare_threshold, compare_rerank)):
        _validate_topk(topk)
        _validate_threshold(threshold)
        return [
            EvalExperimentConfig(
                name=_build_experiment_name(topk, threshold, rerank_enabled),
                topk=topk,
                threshold=threshold,
                rerank_enabled=rerank_enabled,
            )
        ]

    topk_values = _parse_topk_values(compare_topk) if compare_topk is not None else [topk]
    threshold_values = (
        _parse_threshold_values(compare_threshold)
        if compare_threshold is not None
        else [threshold]
    )
    rerank_values = (
        _parse_bool_values(compare_rerank) if compare_rerank is not None else [rerank_enabled]
    )

    deduplicated: list[EvalExperimentConfig] = []
    seen: set[tuple[int, float | None, bool]] = set()
    for current_topk, current_threshold, current_rerank in product(
        topk_values, threshold_values, rerank_values
    ):
        key = (current_topk, current_threshold, current_rerank)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(
            EvalExperimentConfig(
                name=_build_experiment_name(
                    current_topk, current_threshold, current_rerank
                ),
                topk=current_topk,
                threshold=current_threshold,
                rerank_enabled=current_rerank,
            )
        )
    return deduplicated


def run_experiments(
    *,
    kb_id: str,
    eval_set: EvalSet,
    configs: list[EvalExperimentConfig],
    settings,
) -> list[EvalExperimentResult]:
    """按顺序执行多组实验并返回结果。"""

    results: list[EvalExperimentResult] = []
    for config in configs:
        result, item_results = run_eval_with_details(
            kb_id=kb_id,
            eval_set=eval_set,
            topk=config.topk,
            threshold=config.threshold,
            rerank_enabled=config.rerank_enabled,
            settings=settings,
        )
        results.append(
            EvalExperimentResult(
                config=config,
                result=result,
                item_results=item_results,
            )
        )
    return results


def load_eval_set(path: Path) -> EvalSet:
    """加载评测集 JSON 文件。"""

    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("name") or path.stem
    items_data = data.get("items") or []
    items: list[EvalItem] = []
    for item in items_data:
        items.append(
            EvalItem(
                question=item["question"],
                gold_doc_id=item.get("gold_doc_id"),
                gold_page_start=item.get("gold_page_start"),
                gold_page_end=item.get("gold_page_end"),
                gold_doc_name=item.get("gold_doc_name"),
            )
        )
    return EvalSet(name=name, items=items)


def _single_result_payload(
    *,
    eval_set_name: str,
    kb_id: str,
    config: EvalExperimentConfig,
    result: EvalResult,
    items: list[EvalItemResult] | None,
) -> dict[str, object]:
    """构建单次评测输出。"""

    payload = {
        "eval_set": eval_set_name,
        "kb_id": kb_id,
        "topk": config.topk,
        "threshold": config.threshold,
        "rerank_enabled": config.rerank_enabled,
        "samples": result.samples,
        "recall_at_k": result.recall_at_k,
        "mrr": result.mrr,
        "avg_ms": result.avg_ms,
        "p95_ms": result.p95_ms,
        "diagnostics": _build_item_diagnostics(items or []),
    }
    if items is not None:
        payload["items"] = [_item_result_payload(item) for item in items]
    return payload


def _compare_result_payload(
    *,
    eval_set_name: str,
    kb_id: str,
    experiments: list[EvalExperimentResult],
    show_items: bool,
) -> dict[str, object]:
    """构建多组参数对比输出。"""

    ranked = sorted(
        experiments,
        key=lambda item: (
            -item.result.recall_at_k,
            -item.result.mrr,
            item.result.avg_ms,
            item.result.p95_ms,
        ),
    )
    fastest = min(experiments, key=lambda item: (item.result.avg_ms, item.result.p95_ms))
    return {
        "eval_set": eval_set_name,
        "kb_id": kb_id,
        "experiment_count": len(experiments),
        "summary": {
            "best_overall": _experiment_payload(ranked[0], show_items=show_items),
            "fastest": _experiment_payload(fastest, show_items=show_items),
        },
        "experiments": [_experiment_payload(item, show_items=show_items) for item in ranked],
    }


def _experiment_payload(
    item: EvalExperimentResult,
    *,
    show_items: bool,
) -> dict[str, object]:
    """将实验结果格式化为可序列化输出。"""

    payload = {
        "name": item.config.name,
        "topk": item.config.topk,
        "threshold": item.config.threshold,
        "rerank_enabled": item.config.rerank_enabled,
        **asdict(item.result),
        "diagnostics": _build_item_diagnostics(item.item_results),
    }
    if show_items:
        payload["items"] = [_item_result_payload(detail) for detail in item.item_results]
    return payload


def _item_result_payload(item: EvalItemResult) -> dict[str, object]:
    """格式化单题评测明细。"""

    return asdict(item)


def _build_item_diagnostics(items: list[EvalItemResult]) -> dict[str, int]:
    """聚合逐题明细，输出阈值与重排诊断摘要。"""

    raw_match_count = sum(1 for item in items if item.raw_rank is not None)
    threshold_match_count = sum(1 for item in items if item.threshold_rank is not None)
    final_match_count = sum(1 for item in items if item.rank is not None)
    threshold_filtered_relevant_count = sum(
        1
        for item in items
        if item.raw_rank is not None and item.threshold_rank is None
    )
    rerank_promoted_count = sum(
        1
        for item in items
        if item.threshold_rank is not None
        and item.rank is not None
        and item.rank < item.threshold_rank
    )
    rerank_demoted_count = sum(
        1
        for item in items
        if item.threshold_rank is not None
        and item.rank is not None
        and item.rank > item.threshold_rank
    )
    top1_hit_count = sum(1 for item in items if item.rank == 1)
    return {
        "raw_match_count": raw_match_count,
        "threshold_match_count": threshold_match_count,
        "final_match_count": final_match_count,
        "threshold_filtered_relevant_count": threshold_filtered_relevant_count,
        "rerank_promoted_count": rerank_promoted_count,
        "rerank_demoted_count": rerank_demoted_count,
        "top1_hit_count": top1_hit_count,
    }


def _parse_topk_values(raw: str) -> list[int]:
    """解析批量实验的 TopK 列表。"""

    values: list[int] = []
    for part in _split_csv(raw):
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"非法 topk 值: {part}") from exc
        _validate_topk(value)
        values.append(value)
    return values


def _parse_threshold_values(raw: str) -> list[float | None]:
    """解析批量实验的 threshold 列表。"""

    values: list[float | None] = []
    for part in _split_csv(raw):
        normalized = part.lower()
        if normalized in {"none", "null"}:
            values.append(None)
            continue
        try:
            value = float(part)
        except ValueError as exc:
            raise ValueError(f"非法 threshold 值: {part}") from exc
        _validate_threshold(value)
        values.append(value)
    return values


def _parse_bool_values(raw: str) -> list[bool]:
    """解析批量实验的布尔开关列表。"""

    values: list[bool] = []
    for part in _split_csv(raw):
        normalized = part.lower()
        if normalized in {"true", "1", "yes", "y"}:
            values.append(True)
            continue
        if normalized in {"false", "0", "no", "n"}:
            values.append(False)
            continue
        raise ValueError(f"非法 rerank 开关值: {part}")
    return values


def _split_csv(raw: str) -> list[str]:
    """拆分逗号分隔参数，并过滤空白项。"""

    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("批量实验参数不能为空")
    return values


def _validate_topk(value: int) -> None:
    """校验 TopK 范围。"""

    if value <= 0:
        raise ValueError("topk 必须大于 0")


def _validate_threshold(value: float | None) -> None:
    """校验阈值范围。"""

    if value is None:
        return
    if value < 0 or value > 1:
        raise ValueError("threshold 必须位于 0 到 1 之间")


def _build_experiment_name(
    topk: int, threshold: float | None, rerank_enabled: bool
) -> str:
    """生成实验结果名称，便于比较输出阅读。"""

    threshold_text = "none" if threshold is None else f"{threshold:.2f}"
    rerank_text = "true" if rerank_enabled else "false"
    return f"topk={topk}|threshold={threshold_text}|rerank={rerank_text}"


if __name__ == "__main__":
    main()
