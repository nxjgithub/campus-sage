from __future__ import annotations

import json
from pathlib import Path

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.eval.dto import EvalCandidatePreview, EvalItem, EvalItemResult, EvalResult, EvalSet
from scripts.run_eval import (
    EvalExperimentConfig,
    build_experiment_configs,
    build_effective_settings,
    format_eval_runtime_error,
    load_eval_set,
    _build_item_diagnostics,
    _single_result_payload,
    run_experiments,
)


class _DummySettings:
    """占位设置对象，供脚本层测试透传使用。"""


def test_build_experiment_configs_for_single_run() -> None:
    configs = build_experiment_configs(
        topk=5,
        threshold=0.25,
        rerank_enabled=False,
        compare_topk=None,
        compare_threshold=None,
        compare_rerank=None,
    )

    assert configs == [
        EvalExperimentConfig(
            name="topk=5|threshold=0.25|rerank=false",
            topk=5,
            threshold=0.25,
            rerank_enabled=False,
        )
    ]


def test_build_experiment_configs_for_compare_matrix() -> None:
    configs = build_experiment_configs(
        topk=5,
        threshold=None,
        rerank_enabled=False,
        compare_topk="3,5",
        compare_threshold="none,0.2",
        compare_rerank="false,true",
    )

    assert len(configs) == 8
    assert configs[0].name == "topk=3|threshold=none|rerank=false"
    assert configs[-1].name == "topk=5|threshold=0.20|rerank=true"


def test_build_experiment_configs_rejects_invalid_threshold() -> None:
    try:
        build_experiment_configs(
            topk=5,
            threshold=None,
            rerank_enabled=False,
            compare_topk=None,
            compare_threshold="1.5",
            compare_rerank=None,
        )
    except ValueError as exc:
        assert "threshold" in str(exc)
    else:
        raise AssertionError("应当拒绝非法 threshold")


def test_run_experiments_runs_all_configs(monkeypatch) -> None:
    calls: list[tuple[int, float | None, bool]] = []

    def _fake_run_eval_with_details(**kwargs) -> tuple[EvalResult, list[EvalItemResult]]:
        calls.append(
            (kwargs["topk"], kwargs["threshold"], kwargs["rerank_enabled"])
        )
        return (
            EvalResult(
                recall_at_k=1.0,
                mrr=1.0,
                avg_ms=12,
                p95_ms=12,
                samples=1,
            ),
            [
                EvalItemResult(
                    question="问题",
                    gold_doc_id="doc_1",
                    gold_doc_name=None,
                    rank=1,
                    raw_rank=1,
                    threshold_rank=1,
                    retrieve_ms=12,
                    raw_hit_count=1,
                    threshold_hit_count=1,
                    final_hit_count=1,
                    top_candidates=[
                        EvalCandidatePreview(
                            rank=1,
                            doc_id="doc_1",
                            doc_name="demo.pdf",
                            score=0.99,
                            matched=True,
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr("scripts.run_eval.run_eval_with_details", _fake_run_eval_with_details)
    results = run_experiments(
        kb_id="kb_demo",
        eval_set=EvalSet(
            name="demo",
            items=[
                EvalItem(
                    question="问题",
                    gold_doc_id="doc_1",
                    gold_page_start=1,
                    gold_page_end=1,
                )
            ],
        ),
        configs=[
            EvalExperimentConfig(
                name="topk=3|threshold=none|rerank=false",
                topk=3,
                threshold=None,
                rerank_enabled=False,
            ),
            EvalExperimentConfig(
                name="topk=5|threshold=0.20|rerank=true",
                topk=5,
                threshold=0.2,
                rerank_enabled=True,
            ),
        ],
        settings=_DummySettings(),
    )

    assert len(results) == 2
    assert calls == [(3, None, False), (5, 0.2, True)]
    assert results[0].item_results[0].rank == 1


def test_load_eval_set_supports_gold_doc_name(tmp_path: Path) -> None:
    eval_file = tmp_path / "eval.json"
    eval_file.write_text(
        json.dumps(
            {
                "name": "demo_eval",
                "items": [
                    {
                        "question": "补考资格通常适用于哪些学生情形？",
                        "gold_doc_name": "本科生考试管理规定.pdf",
                        "gold_doc_id": None,
                        "gold_page_start": 7,
                        "gold_page_end": 8,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    eval_set = load_eval_set(eval_file)

    assert eval_set.name == "demo_eval"
    assert eval_set.items[0].gold_doc_id is None
    assert eval_set.items[0].gold_doc_name == "本科生考试管理规定.pdf"


def test_build_effective_settings_applies_cli_overrides() -> None:
    base_settings = Settings(
        _env_file=None,
        embedding_backend="http",
        embedding_base_url="http://127.0.0.1:8001/v1",
        embedding_api_path="/embeddings",
        vector_backend="qdrant",
        qdrant_url="http://127.0.0.1:6333",
    )

    effective_settings = build_effective_settings(
        base_settings=base_settings,
        embedding_backend="simple",
        embedding_base_url=None,
        embedding_api_path=None,
        vector_backend=None,
        qdrant_url=None,
    )

    assert effective_settings.embedding_backend == "simple"
    assert effective_settings.embedding_base_url == "http://127.0.0.1:8001/v1"
    assert base_settings.embedding_backend == "http"


def test_format_eval_runtime_error_for_http_embedding() -> None:
    settings = Settings(
        _env_file=None,
        embedding_backend="http",
        embedding_base_url="http://127.0.0.1:8001/v1",
        embedding_api_path="/embeddings",
    )

    message = format_eval_runtime_error(
        AppError(
            code=ErrorCode.EMBEDDING_FAILED,
            message="Embedding 服务不可用",
            detail={"error": "connect refused"},
            status_code=500,
        ),
        settings,
    )

    assert "评测执行失败" in message
    assert "backend=http" in message
    assert "--embedding-backend simple" in message


def test_single_result_payload_can_include_item_details() -> None:
    payload = _single_result_payload(
        eval_set_name="demo_eval",
        kb_id="kb_demo",
        config=EvalExperimentConfig(
            name="topk=5|threshold=none|rerank=true",
            topk=5,
            threshold=None,
            rerank_enabled=True,
        ),
        result=EvalResult(
            recall_at_k=1.0,
            mrr=1.0,
            avg_ms=12,
            p95_ms=12,
            samples=1,
        ),
        items=[
            EvalItemResult(
                question="补考资格通常适用于哪些学生情形？",
                gold_doc_id=None,
                gold_doc_name="本科生考试管理规定.md",
                rank=1,
                raw_rank=3,
                threshold_rank=3,
                retrieve_ms=18,
                raw_hit_count=8,
                threshold_hit_count=8,
                final_hit_count=5,
                top_candidates=[
                    EvalCandidatePreview(
                        rank=1,
                        doc_id="doc_other",
                        doc_name="其他文档.md",
                        score=0.93,
                        matched=False,
                    )
                ],
            )
        ],
    )

    assert payload["items"][0]["question"] == "补考资格通常适用于哪些学生情形？"
    assert payload["items"][0]["raw_rank"] == 3
    assert payload["items"][0]["top_candidates"][0]["matched"] is False
    assert payload["diagnostics"]["raw_match_count"] == 1
    assert payload["diagnostics"]["top1_hit_count"] == 1


def test_build_item_diagnostics_summarizes_threshold_and_rerank() -> None:
    diagnostics = _build_item_diagnostics(
        [
            EvalItemResult(
                question="题目1",
                gold_doc_id=None,
                gold_doc_name="doc_a.md",
                rank=None,
                raw_rank=2,
                threshold_rank=None,
                retrieve_ms=10,
                raw_hit_count=8,
                threshold_hit_count=0,
                final_hit_count=0,
                top_candidates=[],
            ),
            EvalItemResult(
                question="题目2",
                gold_doc_id=None,
                gold_doc_name="doc_b.md",
                rank=1,
                raw_rank=3,
                threshold_rank=2,
                retrieve_ms=11,
                raw_hit_count=8,
                threshold_hit_count=5,
                final_hit_count=5,
                top_candidates=[],
            ),
            EvalItemResult(
                question="题目3",
                gold_doc_id=None,
                gold_doc_name="doc_c.md",
                rank=2,
                raw_rank=1,
                threshold_rank=1,
                retrieve_ms=12,
                raw_hit_count=8,
                threshold_hit_count=5,
                final_hit_count=5,
                top_candidates=[],
            ),
        ]
    )

    assert diagnostics["raw_match_count"] == 3
    assert diagnostics["threshold_match_count"] == 2
    assert diagnostics["final_match_count"] == 2
    assert diagnostics["threshold_filtered_relevant_count"] == 1
    assert diagnostics["rerank_promoted_count"] == 1
    assert diagnostics["rerank_demoted_count"] == 1
    assert diagnostics["top1_hit_count"] == 1
