from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ingest.chunker import Chunker
from app.ingest.parser import DocumentParser


POINT_NAMESPACE = UUID("57f77fb8-1ab8-41bb-b4f7-438f68f71f89")


@dataclass(slots=True)
class ChunkEntry:
    """向量实验中的文本块。"""

    vector: list[float]
    doc_name: str


def main() -> None:
    """运行 V11 分块向量召回实验。"""

    parser = argparse.ArgumentParser(description="运行 V11 正式文件分块向量召回实验")
    parser.add_argument("--manifest-file", default="docs/examples/official_formal_corpus_v11_manifest.json")
    parser.add_argument("--eval-file", default="docs/examples/eval_set_official_formal_v11.json")
    parser.add_argument("--output-file", default="outputs/eval_official_formal_v11_fast/chunk_vector_experiment.json")
    parser.add_argument("--model-name", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", str(ROOT_DIR / "data" / "hf_cache"))
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model_name, device="cpu", local_files_only=True)
    manifest = json.loads((ROOT_DIR / args.manifest_file).read_text(encoding="utf-8"))
    eval_set = json.loads((ROOT_DIR / args.eval_file).read_text(encoding="utf-8"))
    questions = [item for item in eval_set["items"] if item.get("gold_doc_name")]
    question_vectors = encode(model, [item["question"] for item in questions], args.batch_size)

    results = []
    for group, chunk_size, chunk_overlap, description in [
        ("A", 300, 50, "细粒度分块"),
        ("B", 500, 100, "默认分块"),
        ("C", 800, 150, "大粒度分块"),
    ]:
        start = time.perf_counter()
        chunks, doc_count = build_chunks(
            manifest=manifest,
            model=model,
            batch_size=args.batch_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ranks = []
        for item, query_vector in zip(questions, question_vectors, strict=True):
            hits = search(chunks, query_vector, topk=20)
            ranks.append(first_rank(hits, item["gold_doc_name"]))
        results.append(
            {
                "group": group,
                "description": description,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "document_count": doc_count,
                "chunk_count": len(chunks),
                "build_ms": elapsed_ms,
                "recall_at_5": recall_at(ranks, 5),
                "recall_at_10": recall_at(ranks, 10),
                "recall_at_20": recall_at(ranks, 20),
                "mrr_at_20": mrr_at(ranks, 20),
                "top1_hit_count": sum(1 for rank in ranks if rank == 1),
                "samples": len(ranks),
            }
        )
        print(f"finished chunk group {group}: {len(chunks)} chunks", flush=True)

    payload = {
        "model_name": args.model_name,
        "eval_file": args.eval_file,
        "manifest_file": args.manifest_file,
        "results": results,
    }
    output_file = ROOT_DIR / args.output_file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_chunks(
    *,
    manifest: dict[str, Any],
    model: Any,
    batch_size: int,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[ChunkEntry], int]:
    """按指定分块参数构建向量文本块。"""

    parser = DocumentParser()
    chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    texts: list[str] = []
    doc_names: list[str] = []
    for document in manifest["documents"]:
        path = ROOT_DIR / document["source_path"]
        pages = parser.parse(path)
        chunks = chunker.build(pages)
        doc_id = uuid5(POINT_NAMESPACE, path.name).hex
        for chunk in chunks:
            texts.append(f"{path.name}\n{chunk.section_path or ''}\n{chunk.text}\n{doc_id}")
            doc_names.append(path.name)
    vectors = encode(model, texts, batch_size)
    return [
        ChunkEntry(vector=vector, doc_name=doc_name)
        for vector, doc_name in zip(vectors, doc_names, strict=True)
    ], len(manifest["documents"])


def encode(model: Any, texts: list[str], batch_size: int) -> list[list[float]]:
    """批量编码文本。"""

    vectors = model.encode(
        texts,
        batch_size=max(1, batch_size),
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [list(map(float, vector)) for vector in vectors]


def search(chunks: list[ChunkEntry], query_vector: list[float], topk: int) -> list[tuple[str, float]]:
    """执行向量检索。"""

    hits = [(chunk.doc_name, cosine(query_vector, chunk.vector)) for chunk in chunks]
    hits.sort(key=lambda item: item[1], reverse=True)
    return hits[:topk]


def first_rank(hits: list[tuple[str, float]], gold_doc_name: str) -> int | None:
    """返回标准文档首次命中的位置。"""

    for index, (doc_name, _) in enumerate(hits, start=1):
        if doc_name == gold_doc_name:
            return index
    return None


def recall_at(ranks: list[int | None], topk: int) -> float:
    """计算 Recall@K。"""

    return round(sum(1 for rank in ranks if rank is not None and rank <= topk) / len(ranks), 4)


def mrr_at(ranks: list[int | None], topk: int) -> float:
    """计算 MRR@K。"""

    return round(
        sum(1 / rank for rank in ranks if rank is not None and rank <= topk) / len(ranks),
        4,
    )


def cosine(left: list[float], right: list[float]) -> float:
    """计算余弦相似度。"""

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


if __name__ == "__main__":
    main()
