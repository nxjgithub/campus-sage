from __future__ import annotations

import json
from pathlib import Path

from app.eval.dto import EvalItem, EvalResult, EvalSet
from scripts.run_eval import (
    EvalExperimentConfig,
    build_experiment_configs,
    load_eval_set,
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

    def _fake_run_eval(**kwargs) -> EvalResult:
        calls.append(
            (kwargs["topk"], kwargs["threshold"], kwargs["rerank_enabled"])
        )
        return EvalResult(
            recall_at_k=1.0,
            mrr=1.0,
            avg_ms=12,
            p95_ms=12,
            samples=1,
        )

    monkeypatch.setattr("scripts.run_eval.run_eval", _fake_run_eval)
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
