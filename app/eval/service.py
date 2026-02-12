"""评测相关服务。"""

from __future__ import annotations

import json
from dataclasses import asdict

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.core.utils import new_id, utc_now_iso
from app.db.models import (
    EvalItemRecord,
    EvalResultRecord,
    EvalRunRecord,
    EvalSetRecord,
)
from app.db.repos.interfaces import (
    EvalItemRepositoryProtocol,
    EvalResultRepositoryProtocol,
    EvalRunRepositoryProtocol,
    EvalSetRepositoryProtocol,
    KnowledgeBaseRepositoryProtocol,
)
from app.eval.dto import EvalItem, EvalResult, EvalSet
from app.eval.metrics import mean_reciprocal_rank, percentile, recall_at_k
from app.eval.runner import evaluate_items


class EvalService:
    """评测服务。"""

    def __init__(
        self,
        eval_set_repo: EvalSetRepositoryProtocol,
        eval_item_repo: EvalItemRepositoryProtocol,
        eval_run_repo: EvalRunRepositoryProtocol,
        eval_result_repo: EvalResultRepositoryProtocol,
        kb_repo: KnowledgeBaseRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._eval_set_repo = eval_set_repo
        self._eval_item_repo = eval_item_repo
        self._eval_run_repo = eval_run_repo
        self._eval_result_repo = eval_result_repo
        self._kb_repo = kb_repo
        self._settings = settings

    def create_eval_set(
        self,
        name: str,
        description: str | None,
        items: list[dict[str, object]],
    ) -> tuple[EvalSetRecord, list[EvalItemRecord]]:
        """创建评测集并写入样本。"""

        if not name.strip():
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="评测集名称不能为空",
                detail=None,
                status_code=400,
            )
        if not items:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="评测集样本不能为空",
                detail=None,
                status_code=400,
            )
        now = utc_now_iso()
        eval_set_id = new_id("es")
        record = EvalSetRecord(
            eval_set_id=eval_set_id,
            name=name.strip(),
            description=description,
            created_at=now,
        )
        self._eval_set_repo.create(record)
        item_records = self._build_item_records(eval_set_id, items, now)
        self._eval_item_repo.create_many(item_records)
        return record, item_records

    def run_eval(
        self,
        eval_set_id: str,
        kb_id: str,
        topk: int,
        threshold: float | None,
        rerank_enabled: bool,
    ) -> tuple[EvalRunRecord, EvalResult]:
        """执行评测并保存结果。"""

        eval_set_record = self._eval_set_repo.get(eval_set_id)
        if eval_set_record is None:
            raise AppError(
                code=ErrorCode.EVAL_SET_NOT_FOUND,
                message="评测集不存在",
                detail={"eval_set_id": eval_set_id},
                status_code=404,
            )
        kb_record = self._kb_repo.get(kb_id)
        if kb_record is None or kb_record.deleted:
            raise AppError(
                code=ErrorCode.KB_NOT_FOUND,
                message="知识库不存在",
                detail={"kb_id": kb_id},
                status_code=404,
            )
        if topk <= 0:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="TopK 必须大于 0",
                detail={"topk": topk},
                status_code=400,
            )

        item_records = self._eval_item_repo.list_by_set(eval_set_id)
        if not item_records:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="评测集没有样本",
                detail={"eval_set_id": eval_set_id},
                status_code=400,
            )
        eval_set = EvalSet(
            name=eval_set_record.name,
            items=[
                EvalItem(
                    question=item.question,
                    gold_doc_id=item.gold_doc_id or "",
                    gold_page_start=item.gold_page_start,
                    gold_page_end=item.gold_page_end,
                )
                for item in item_records
            ],
        )
        item_results = evaluate_items(
            kb_id=kb_id,
            eval_set=eval_set,
            topk=topk,
            settings=self._settings,
            rerank_enabled=rerank_enabled,
            threshold=threshold,
        )
        metrics = _build_metrics(item_results, topk)

        now = utc_now_iso()
        run_record = EvalRunRecord(
            run_id=new_id("erun"),
            eval_set_id=eval_set_id,
            kb_id=kb_id,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
            metrics_json=json.dumps(asdict(metrics), ensure_ascii=False),
            created_at=now,
        )
        self._eval_run_repo.create(run_record)
        result_records = [
            EvalResultRecord(
                run_result_id=new_id("eres"),
                run_id=run_record.run_id,
                eval_item_id=item.eval_item_id,
                hit=result.rank is not None,
                rank=result.rank,
                retrieve_ms=result.retrieve_ms,
                notes=None,
                created_at=now,
            )
            for item, result in zip(item_records, item_results)
        ]
        self._eval_result_repo.create_many(result_records)
        return run_record, metrics

    def get_run(self, run_id: str) -> tuple[EvalRunRecord, EvalResult | None]:
        """获取评测运行记录。"""

        record = self._eval_run_repo.get(run_id)
        if record is None:
            raise AppError(
                code=ErrorCode.EVAL_RUN_NOT_FOUND,
                message="评测运行不存在",
                detail={"run_id": run_id},
                status_code=404,
            )
        metrics = _load_metrics(record.metrics_json)
        return record, metrics

    def _build_item_records(
        self, eval_set_id: str, items: list[dict[str, object]], created_at: str
    ) -> list[EvalItemRecord]:
        """构建评测样本记录。"""

        records: list[EvalItemRecord] = []
        for item in items:
            question = str(item.get("question") or "").strip()
            if not question:
                raise AppError(
                    code=ErrorCode.VALIDATION_FAILED,
                    message="评测样本问题不能为空",
                    detail={"item": item},
                    status_code=400,
                )
            gold_doc_id = item.get("gold_doc_id")
            gold_page_start = item.get("gold_page_start")
            gold_page_end = item.get("gold_page_end")
            if (
                gold_page_start is not None
                and gold_page_end is not None
                and int(gold_page_end) < int(gold_page_start)
            ):
                raise AppError(
                    code=ErrorCode.VALIDATION_FAILED,
                    message="评测样本页码区间非法",
                    detail={"item": item},
                    status_code=400,
                )
            tags = item.get("tags")
            tags_json = json.dumps(tags, ensure_ascii=False) if tags is not None else None
            records.append(
                EvalItemRecord(
                    eval_item_id=new_id("eitem"),
                    eval_set_id=eval_set_id,
                    question=question,
                    gold_doc_id=str(gold_doc_id) if gold_doc_id else None,
                    gold_page_start=gold_page_start,
                    gold_page_end=gold_page_end,
                    tags_json=tags_json,
                    created_at=created_at,
                )
            )
        return records


def _build_metrics(item_results: list, topk: int) -> EvalResult:
    """汇总评测指标。"""

    ranks = [item.rank for item in item_results]
    durations = [item.retrieve_ms for item in item_results]
    return EvalResult(
        recall_at_k=recall_at_k(ranks, topk),
        mrr=mean_reciprocal_rank(ranks),
        avg_ms=int(sum(durations) / len(durations)) if durations else 0,
        p95_ms=percentile(durations, 95),
        samples=len(item_results),
    )


def _load_metrics(payload: str | None) -> EvalResult | None:
    """解析评测指标 JSON。"""

    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return EvalResult(
        recall_at_k=float(data.get("recall_at_k", 0.0)),
        mrr=float(data.get("mrr", 0.0)),
        avg_ms=int(data.get("avg_ms", 0)),
        p95_ms=int(data.get("p95_ms", 0)),
        samples=int(data.get("samples", 0)),
    )
