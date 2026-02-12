from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.settings import get_settings
from app.eval.dto import EvalItem, EvalSet
from app.eval.runner import run_eval


def main() -> None:
    """评测脚本入口。"""

    parser = argparse.ArgumentParser(description="运行 CampusSage 评测")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument("--eval-file", required=True, help="评测集 JSON 文件路径")
    parser.add_argument("--topk", type=int, default=5, help="检索 TopK")
    args = parser.parse_args()

    eval_set = load_eval_set(Path(args.eval_file))
    settings = get_settings()
    result = run_eval(
        kb_id=args.kb_id,
        eval_set=eval_set,
        topk=args.topk,
        settings=settings,
    )
    output = {
        "eval_set": eval_set.name,
        "kb_id": args.kb_id,
        "topk": args.topk,
        "samples": result.samples,
        "recall_at_k": result.recall_at_k,
        "mrr": result.mrr,
        "avg_ms": result.avg_ms,
        "p95_ms": result.p95_ms,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


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
                gold_doc_id=item["gold_doc_id"],
                gold_page_start=item.get("gold_page_start"),
                gold_page_end=item.get("gold_page_end"),
            )
        )
    return EvalSet(name=name, items=items)


if __name__ == "__main__":
    main()
