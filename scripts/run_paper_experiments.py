from __future__ import annotations

# ruff: noqa: E402

import argparse
import csv
import json
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID, uuid5

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.settings import get_settings
from app.core.utils import utc_now_iso
from app.ingest.chunker import Chunker
from app.ingest.parser import DocumentParser
from app.rag.embedding import HttpEmbeddingClient
from app.rag.reranker import SimpleReranker
from app.rag.vector_store import VectorHit


POINT_NAMESPACE = UUID("57f77fb8-1ab8-41bb-b4f7-438f68f71f89")
DEFAULT_EVAL_FILE = ROOT_DIR / "outputs" / "eval_official_20260506" / "eval_set_official.json"
DEFAULT_SOURCE_DIR = ROOT_DIR / "data" / "正式文件"
DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
CHUNK_GROUPS = (
    ("A", 300, 50, "细粒度分块"),
    ("B", 500, 100, "中等分块"),
    ("C", 800, 150, "较大分块"),
)
THRESHOLD_GROUPS = (
    ("A", 0.20, "宽松阈值，容易回答"),
    ("B", 0.30, "中等阈值"),
    ("C", 0.40, "严格阈值"),
    ("D", 0.50, "高严格度，容易拒答"),
)


@dataclass(slots=True)
class EvalQuestion:
    """论文实验使用的评测问题。"""

    question: str
    expected: str
    question_type: str
    gold_doc_name: str | None


@dataclass(slots=True)
class IndexedKb:
    """一组分块参数对应的 Qdrant 知识库索引。"""

    group: str
    kb_id: str
    chunk_size: int
    chunk_overlap: int
    description: str
    collection_name: str
    chunk_count: int
    ingest_ms: int
    docs: list[dict[str, Any]]


@dataclass(slots=True)
class RetrievalCase:
    """单题检索与拒答判定明细。"""

    question: str
    expected: str
    question_type: str
    gold_doc_name: str | None
    refused: bool
    refusal_reason: str | None
    citation_accurate: bool
    rank: int | None
    raw_rank: int | None
    threshold_rank: int | None
    retrieve_ms: int
    top_score: float | None
    citations: list[dict[str, Any]]


class SentenceEmbeddingModel:
    """基于 sentence-transformers 的真实本地向量模型。"""

    def __init__(self, model_name: str, batch_size: int, device: str) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self._model = self._load_model()
        self.vector_dim = self._detect_vector_dim()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文本。"""

        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return _normalize_vectors(vectors)

    def embed_query(self, text: str) -> list[float]:
        """向量化查询。"""

        return self.embed_texts([text])[0]

    def _load_model(self) -> Any:
        """加载真实语义向量模型，缺失时给出明确错误。"""

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "缺少 sentence-transformers，请先用 .venv 安装依赖。"
            ) from exc
        return SentenceTransformer(self.model_name, device=self.device)

    def _detect_vector_dim(self) -> int:
        """探测模型输出维度，避免手工写死。"""

        return len(self.embed_query("维度探测"))


class HttpEmbeddingModel:
    """基于 OpenAI 兼容 HTTP 服务的真实向量模型。"""

    def __init__(
        self,
        *,
        settings,
        base_url: str | None,
        api_path: str | None,
        model_name: str | None,
        batch_size: int,
    ) -> None:
        overrides: dict[str, Any] = {
            "embedding_backend": "http",
            "embedding_batch_size": batch_size,
        }
        if base_url:
            overrides["embedding_base_url"] = base_url
        if api_path:
            overrides["embedding_api_path"] = api_path
        if model_name:
            overrides["embedding_model_name"] = model_name
        self._settings = settings.model_copy(update=overrides)
        self.model_name = self._settings.embedding_model_name
        self.batch_size = batch_size
        self.device = "http"
        self._client = HttpEmbeddingClient(self._settings)
        self.vector_dim = self._detect_vector_dim()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量调用 HTTP Embedding 服务。"""

        return self._client.embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        """调用 HTTP Embedding 服务向量化查询。"""

        return self._client.embed_query(text)

    def _detect_vector_dim(self) -> int:
        """探测 HTTP Embedding 输出维度。"""

        return len(self.embed_query("维度探测"))


class LocalQdrantStore:
    """使用 Qdrant 本地持久化引擎的向量库。"""

    def __init__(self, path: Path, vector_dim: int) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.http import models as rest  # type: ignore

        self.path = path
        self.vector_dim = vector_dim
        self._rest = rest
        self._client = QdrantClient(path=str(path))

    def recreate_collection(self, collection_name: str) -> None:
        """重建集合，保证每组实验从干净索引开始。"""

        if self._client.collection_exists(collection_name):
            self._client.delete_collection(collection_name)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=self._rest.VectorParams(
                size=self.vector_dim,
                distance=self._rest.Distance.COSINE,
            ),
        )

    def upsert(self, collection_name: str, points: list[dict[str, Any]]) -> None:
        """写入一批向量点。"""

        if not points:
            return
        self._client.upsert(
            collection_name=collection_name,
            points=[
                self._rest.PointStruct(
                    id=_point_id(str(item["payload"]["chunk_id"])),
                    vector=item["vector"],
                    payload=item["payload"],
                )
                for item in points
            ],
            wait=True,
        )

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorHit]:
        """执行向量检索并转换为项目内部命中结构。"""

        search = getattr(self._client, "search", None)
        if callable(search):
            results = search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
            )
        else:
            response = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            )
            results = response.points
        return [
            VectorHit(score=float(item.score), payload=dict(item.payload or {}))
            for item in results
        ]

    def close(self) -> None:
        """关闭 Qdrant 本地库，释放文件锁。"""

        self._client.close()


class RemoteQdrantStore:
    """使用 Docker 中 Qdrant 服务端的向量库。"""

    def __init__(self, url: str, vector_dim: int) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.http import models as rest  # type: ignore

        self.url = url
        self.vector_dim = vector_dim
        self._rest = rest
        self._client = QdrantClient(
            url=url,
            check_compatibility=False,
            prefer_grpc=False,
            timeout=60,
            trust_env=False,
        )

    def recreate_collection(self, collection_name: str) -> None:
        """重建 Qdrant 服务端集合。"""

        if self._collection_exists(collection_name):
            self._client.delete_collection(collection_name)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=self._rest.VectorParams(
                size=self.vector_dim,
                distance=self._rest.Distance.COSINE,
            ),
        )

    def upsert(self, collection_name: str, points: list[dict[str, Any]]) -> None:
        """写入 Qdrant 服务端向量点。"""

        if not points:
            return
        self._client.upsert(
            collection_name=collection_name,
            points=[
                self._rest.PointStruct(
                    id=_point_id(str(item["payload"]["chunk_id"])),
                    vector=item["vector"],
                    payload=item["payload"],
                )
                for item in points
            ],
            wait=True,
        )

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorHit]:
        """在 Qdrant 服务端执行向量检索。"""

        return self._search_rest(collection_name, query_vector, limit)

    def close(self) -> None:
        """关闭 Qdrant 服务端客户端连接。"""

        self._client.close()

    def _search_rest(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorHit]:
        """使用 REST 搜索接口，兼容 Qdrant v1.9.x 响应格式。"""

        response = httpx.post(
            f"{self.url.rstrip('/')}/collections/{collection_name}/points/search",
            json={
                "vector": query_vector,
                "limit": limit,
                "with_payload": True,
            },
            timeout=60,
            trust_env=False,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("result") or []
        return [
            VectorHit(score=float(item.get("score", 0.0)), payload=item.get("payload") or {})
            for item in results
        ]

    def _search_client(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorHit]:
        """保留客户端检索实现，便于后续升级 Qdrant 后切回。"""

        search = getattr(self._client, "search", None)
        if callable(search):
            results = search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
            )
        else:
            response = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            )
            results = response.points
        return [
            VectorHit(score=float(item.score), payload=dict(item.payload or {}))
            for item in results
        ]

    def _collection_exists(self, collection_name: str) -> bool:
        """兼容不同 qdrant-client 版本的集合存在性判断。"""

        collection_exists = getattr(self._client, "collection_exists", None)
        if callable(collection_exists):
            return bool(collection_exists(collection_name))
        collections = self._client.get_collections().collections
        return collection_name in {collection.name for collection in collections}


def main() -> None:
    """运行论文补充实验并写入 outputs。"""

    parser = argparse.ArgumentParser(description="运行 CampusSage 论文补充实验")
    parser.add_argument("--eval-file", default=str(DEFAULT_EVAL_FILE), help="评测集 JSON")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="原始文档目录")
    parser.add_argument("--output-dir", default=None, help="实验输出目录")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="本地向量模型名")
    parser.add_argument(
        "--embedding-backend",
        choices=("local", "http"),
        default="local",
        help="向量化后端：local 使用本地 sentence-transformers，http 使用 TEI/OpenAI 兼容服务",
    )
    parser.add_argument("--embedding-base-url", default=None, help="HTTP Embedding 服务地址")
    parser.add_argument("--embedding-api-path", default=None, help="HTTP Embedding 接口路径")
    parser.add_argument("--device", default="cpu", help="向量模型运行设备")
    parser.add_argument("--batch-size", type=int, default=8, help="向量化批大小")
    parser.add_argument(
        "--vector-backend",
        choices=("local", "remote"),
        default="local",
        help="向量库后端：local 使用 Qdrant 本地持久化，remote 使用 Qdrant 服务端",
    )
    parser.add_argument("--qdrant-url", default=None, help="Qdrant 服务端地址")
    parser.add_argument("--topk", type=int, default=5, help="最终检索 TopK")
    parser.add_argument("--llm-sample-size", type=int, default=20, help="大模型对比样本数")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 RAG 与直接大模型对比")
    parser.add_argument("--keep-qdrant", action="store_true", help="复用输出目录中的 Qdrant 数据")
    args = parser.parse_args()

    output_dir = (
        _resolve_output_dir(Path(args.output_dir))
        if args.output_dir
        else _default_output_dir()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    eval_questions = load_eval_questions(Path(args.eval_file))
    source_dir = Path(args.source_dir)
    doc_names = sorted({item.gold_doc_name for item in eval_questions if item.gold_doc_name})
    if not doc_names:
        raise RuntimeError("评测集缺少 gold_doc_name，无法构建知识库。")

    qdrant_path = output_dir / "qdrant"
    if args.vector_backend == "local" and qdrant_path.exists() and not args.keep_qdrant:
        shutil.rmtree(qdrant_path)

    settings = get_settings()
    if args.embedding_backend == "http":
        embedding = HttpEmbeddingModel(
            settings=settings,
            base_url=args.embedding_base_url,
            api_path=args.embedding_api_path,
            model_name=args.model_name,
            batch_size=args.batch_size,
        )
    else:
        embedding = SentenceEmbeddingModel(args.model_name, args.batch_size, args.device)
    if args.vector_backend == "remote":
        qdrant_url = args.qdrant_url or settings.qdrant_url
        vector_store = RemoteQdrantStore(qdrant_url, embedding.vector_dim)
    else:
        qdrant_url = None
        vector_store = LocalQdrantStore(qdrant_path, embedding.vector_dim)
    try:
        indexed_kbs = [
            build_index(
                group=group,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                description=description,
                source_dir=source_dir,
                doc_names=doc_names,
                embedding=embedding,
                vector_store=vector_store,
            )
            for group, chunk_size, chunk_overlap, description in CHUNK_GROUPS
        ]
        middle_kb = next(item for item in indexed_kbs if item.group == "B")
        chunk_results = run_chunk_experiment(
            indexed_kbs=indexed_kbs,
            questions=[item for item in eval_questions if item.gold_doc_name],
            embedding=embedding,
            vector_store=vector_store,
            topk=args.topk,
        )
        threshold_results = run_threshold_experiment(
            indexed_kb=middle_kb,
            questions=eval_questions,
            embedding=embedding,
            vector_store=vector_store,
            topk=args.topk,
        )
        rerank_results = run_rerank_experiment(
            indexed_kb=middle_kb,
            questions=[item for item in eval_questions if item.gold_doc_name],
            embedding=embedding,
            vector_store=vector_store,
            topk=args.topk,
        )
        llm_results = None
        if not args.skip_llm:
            llm_results = run_llm_comparison(
                indexed_kb=middle_kb,
                questions=select_llm_questions(eval_questions, args.llm_sample_size),
                embedding=embedding,
                vector_store=vector_store,
                topk=args.topk,
                settings=settings,
            )
    finally:
        vector_store.close()

    payload = {
        "generated_at": utc_now_iso(),
        "output_dir": str(output_dir.relative_to(ROOT_DIR)),
        "environment": {
            "embedding_model": args.model_name,
            "embedding_backend": args.embedding_backend,
            "embedding_device": embedding.device,
            "embedding_dim": embedding.vector_dim,
            "vector_database": (
                "Qdrant server mode" if args.vector_backend == "remote" else "Qdrant local persistent mode"
            ),
            "qdrant_url": qdrant_url,
            "qdrant_path": (
                str(qdrant_path.relative_to(ROOT_DIR))
                if args.vector_backend == "local"
                else None
            ),
            "reranker": "SimpleReranker(title + section_path + keyword coverage)",
            "llm_model": settings.vllm_model_name if not args.skip_llm else None,
        },
        "indexed_kbs": [asdict(item) for item in indexed_kbs],
        "experiment_1_chunk": chunk_results,
        "experiment_2_threshold": threshold_results,
        "experiment_3_rerank": rerank_results,
        "experiment_4_llm": llm_results,
    }
    write_json(output_dir / "paper_experiments_summary.json", payload)
    write_markdown_report(output_dir / "paper_experiments_report.md", payload)
    write_sqlite(output_dir / "paper_experiments_metrics.sqlite", payload)
    write_llm_scoring_sheet(output_dir / "llm_manual_scoring_sheet.csv", llm_results)
    print(json.dumps(_console_summary(payload), ensure_ascii=False, indent=2))


def build_index(
    *,
    group: str,
    chunk_size: int,
    chunk_overlap: int,
    description: str,
    source_dir: Path,
    doc_names: list[str],
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
) -> IndexedKb:
    """解析文档、分块、向量化并写入 Qdrant。"""

    parser = DocumentParser()
    chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    kb_id = f"paper_{group.lower()}_{chunk_size}_{chunk_overlap}"
    collection_name = f"paper_{group.lower()}_{chunk_size}_{chunk_overlap}"
    vector_store.recreate_collection(collection_name)

    docs: list[dict[str, Any]] = []
    all_points: list[dict[str, Any]] = []
    start = time.perf_counter()
    for doc_index, doc_name in enumerate(doc_names, start=1):
        path = source_dir / doc_name
        pages = parser.parse(path)
        chunks = chunker.build(pages)
        texts = [chunk.text for chunk in chunks]
        vectors = embedding.embed_texts(texts)
        doc_id = f"doc_{uuid5(POINT_NAMESPACE, doc_name).hex}"
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk_id = f"{kb_id}_{doc_index}_{chunk.chunk_index}"
            payload = {
                "contract_version": "0.1",
                "kb_id": kb_id,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_version": None,
                "published_at": None,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_path": chunk.section_path,
                "chunk_id": chunk_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "source_type": path.suffix.lower().lstrip(".") or "unknown",
                "source_uri": None,
                "hash": str(uuid5(POINT_NAMESPACE, chunk.text)),
                "tokens": len(chunk.text),
                "created_at": utc_now_iso(),
            }
            all_points.append({"vector": vector, "payload": payload})
        docs.append(
            {
                "doc_name": doc_name,
                "doc_id": doc_id,
                "parsed_units": len(pages),
                "chunk_count": len(chunks),
                "char_count": sum(len(page.text) for page in pages),
            }
        )
    for batch in _batch(all_points, 128):
        vector_store.upsert(collection_name, batch)
    ingest_ms = int((time.perf_counter() - start) * 1000)
    return IndexedKb(
        group=group,
        kb_id=kb_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        description=description,
        collection_name=collection_name,
        chunk_count=len(all_points),
        ingest_ms=ingest_ms,
        docs=docs,
    )


def run_chunk_experiment(
    *,
    indexed_kbs: list[IndexedKb],
    questions: list[EvalQuestion],
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
    topk: int,
) -> list[dict[str, Any]]:
    """实验一：比较不同分块参数。"""

    results = []
    for indexed_kb in indexed_kbs:
        cases = [
            retrieve_case(
                indexed_kb=indexed_kb,
                question=item,
                embedding=embedding,
                vector_store=vector_store,
                topk=topk,
                threshold=0.25,
                rerank_enabled=True,
            )
            for item in questions
        ]
        results.append(
            {
                "group": indexed_kb.group,
                "chunk_size": indexed_kb.chunk_size,
                "chunk_overlap": indexed_kb.chunk_overlap,
                "description": indexed_kb.description,
                "chunk_count": indexed_kb.chunk_count,
                "ingest_ms": indexed_kb.ingest_ms,
                **summarize_retrieval_cases(cases, topk),
                "items": [asdict(item) for item in cases],
            }
        )
    return results


def run_threshold_experiment(
    *,
    indexed_kb: IndexedKb,
    questions: list[EvalQuestion],
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
    topk: int,
) -> list[dict[str, Any]]:
    """实验二：比较拒答阈值。"""

    results = []
    for group, threshold, description in THRESHOLD_GROUPS:
        cases = [
            retrieve_case(
                indexed_kb=indexed_kb,
                question=item,
                embedding=embedding,
                vector_store=vector_store,
                topk=topk,
                threshold=threshold,
                rerank_enabled=True,
            )
            for item in questions
        ]
        in_scope = [item for item in cases if item.gold_doc_name]
        out_scope = [item for item in cases if not item.gold_doc_name]
        non_refused = [item for item in cases if not item.refused]
        wrong_answers = [
            item
            for item in non_refused
            if (not item.gold_doc_name) or (item.gold_doc_name and not item.citation_accurate)
        ]
        results.append(
            {
                "group": group,
                "threshold": threshold,
                "description": description,
                "in_scope_refusal_rate": _safe_div(
                    sum(1 for item in in_scope if item.refused),
                    len(in_scope),
                ),
                "out_of_scope_refusal_rate": _safe_div(
                    sum(1 for item in out_scope if item.refused),
                    len(out_scope),
                ),
                "wrong_answer_rate": _safe_div(len(wrong_answers), len(cases)),
                "citation_coverage_rate": _safe_div(
                    sum(1 for item in non_refused if item.citations),
                    len(non_refused),
                ),
                "avg_response_ms": int(mean([item.retrieve_ms for item in cases])) if cases else 0,
                "items": [asdict(item) for item in cases],
            }
        )
    return results


def run_rerank_experiment(
    *,
    indexed_kb: IndexedKb,
    questions: list[EvalQuestion],
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
    topk: int,
) -> list[dict[str, Any]]:
    """实验三：比较是否启用重排。"""

    results = []
    for rerank_enabled in (False, True):
        cases = [
            retrieve_case(
                indexed_kb=indexed_kb,
                question=item,
                embedding=embedding,
                vector_store=vector_store,
                topk=topk,
                threshold=None,
                rerank_enabled=rerank_enabled,
            )
            for item in questions
        ]
        results.append(
            {
                "group": "B" if rerank_enabled else "A",
                "rerank_enabled": rerank_enabled,
                "description": "启用重排" if rerank_enabled else "不启用重排，仅使用向量相似度",
                **summarize_retrieval_cases(cases, topk),
                "top1_hit_rate": _safe_div(sum(1 for item in cases if item.rank == 1), len(cases)),
                "items": [asdict(item) for item in cases],
            }
        )
    return results


def retrieve_case(
    *,
    indexed_kb: IndexedKb,
    question: EvalQuestion,
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
    topk: int,
    threshold: float | None,
    rerank_enabled: bool,
) -> RetrievalCase:
    """执行单题检索、阈值过滤、重排与拒答判定。"""

    search_topk = topk * 4 if rerank_enabled else topk
    start = time.perf_counter()
    query_vector = embedding.embed_query(question.question)
    raw_hits = vector_store.search(indexed_kb.collection_name, query_vector, search_topk)
    raw_rank = first_match_rank(raw_hits, question.gold_doc_name)
    threshold_hits = raw_hits
    if threshold is not None:
        threshold_hits = [hit for hit in raw_hits if hit.score >= threshold]
    threshold_rank = first_match_rank(threshold_hits, question.gold_doc_name)
    final_hits = threshold_hits
    if rerank_enabled:
        final_hits = SimpleReranker().rerank(question.question, final_hits)
    final_hits = final_hits[:topk]
    retrieve_ms = int((time.perf_counter() - start) * 1000)
    rank = first_match_rank(final_hits, question.gold_doc_name)
    refusal_reason = refusal_reason_for(question.question, final_hits, threshold)
    citations = [citation_payload(index, hit) for index, hit in enumerate(final_hits, start=1)]
    citation_accurate = is_citation_accurate(question, citations)
    return RetrievalCase(
        question=question.question,
        expected=question.expected,
        question_type=question.question_type,
        gold_doc_name=question.gold_doc_name,
        refused=refusal_reason is not None,
        refusal_reason=refusal_reason,
        citation_accurate=citation_accurate,
        rank=rank,
        raw_rank=raw_rank,
        threshold_rank=threshold_rank,
        retrieve_ms=retrieve_ms,
        top_score=final_hits[0].score if final_hits else None,
        citations=citations,
    )


def run_llm_comparison(
    *,
    indexed_kb: IndexedKb,
    questions: list[EvalQuestion],
    embedding: SentenceEmbeddingModel,
    vector_store: LocalQdrantStore,
    topk: int,
    settings,
) -> dict[str, Any]:
    """实验四：比较直接大模型与 RAG 回答。"""

    if not settings.vllm_enabled or not settings.vllm_api_key:
        return {"skipped": True, "reason": "未启用 OpenAI 兼容生成模型或缺少 API Key"}
    items: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        direct_start = time.perf_counter()
        direct_answer = call_direct_llm(question.question, settings)
        direct_ms = int((time.perf_counter() - direct_start) * 1000)
        retrieval = retrieve_case(
            indexed_kb=indexed_kb,
            question=question,
            embedding=embedding,
            vector_store=vector_store,
            topk=topk,
            threshold=0.30,
            rerank_enabled=True,
        )
        rag_start = time.perf_counter()
        if retrieval.refused:
            rag_answer = "当前知识库中未找到足够证据，无法给出可靠答案。"
            rag_generate_ms = 0
        else:
            rag_answer = call_rag_llm(question.question, retrieval.citations, settings)
            rag_generate_ms = int((time.perf_counter() - rag_start) * 1000)
        items.append(
            {
                "index": index,
                "question": question.question,
                "question_type": question.question_type,
                "expected": question.expected,
                "gold_doc_name": question.gold_doc_name,
                "direct": {
                    "answer": direct_answer,
                    "elapsed_ms": direct_ms,
                    **score_answer(question, direct_answer, citations=[]),
                },
                "rag": {
                    "answer": rag_answer,
                    "refused": retrieval.refused,
                    "refusal_reason": retrieval.refusal_reason,
                    "citations": retrieval.citations,
                    "retrieve_ms": retrieval.retrieve_ms,
                    "generate_ms": rag_generate_ms,
                    **score_answer(question, rag_answer, citations=retrieval.citations),
                },
            }
        )
    return {
        "skipped": False,
        "sample_count": len(items),
        "direct": summarize_answer_scores([item["direct"] for item in items], questions),
        "rag": summarize_answer_scores([item["rag"] for item in items], questions),
        "items": items,
    }


def call_direct_llm(question: str, settings) -> str:
    """不提供知识库上下文，直接调用生成模型。"""

    payload = {
        "model": settings.vllm_model_name,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是高校事务问答助手，请直接回答用户问题。"},
            {"role": "user", "content": question},
        ],
    }
    return call_chat_completion(payload, settings)


def call_rag_llm(question: str, citations: list[dict[str, Any]], settings) -> str:
    """提供检索证据，调用生成模型生成 RAG 答案。"""

    context = "\n\n".join(
        (
            f"[{item['citation_id']}] 文档：{item['doc_name']}\n"
            f"位置：{item.get('section_path') or item.get('page_start') or '未定位'}\n"
            f"片段：{item['snippet']}"
        )
        for item in citations
    )
    payload = {
        "model": settings.vllm_model_name,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是校园知识库助手，只能基于证据回答。"
                    "回答必须包含引用编号，例如 [1]。证据不足时应拒答。"
                ),
            },
            {"role": "user", "content": f"问题：{question}\n\n证据：\n{context}"},
        ],
    }
    answer = call_chat_completion(payload, settings)
    if citations and not re.search(r"\[\d+\]", answer):
        markers = "".join(f"[{item['citation_id']}]" for item in citations)
        answer = f"{answer}\n\n参考：{markers}"
    return answer


def call_chat_completion(payload: dict[str, Any], settings) -> str:
    """调用 OpenAI 兼容聊天接口。"""

    headers = {"Authorization": f"Bearer {settings.vllm_api_key}"}
    response = httpx.post(
        f"{settings.vllm_base_url.rstrip('/')}/chat/completions",
        json=payload,
        headers=headers,
        timeout=settings.vllm_timeout_s,
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def score_answer(
    question: EvalQuestion,
    answer: str,
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    """用自动代理指标粗评答案，人工评分仍以导出的 CSV 为准。"""

    refused = looks_like_refusal(answer)
    citation_coverage = bool(citations) and bool(re.search(r"\[\d+\]", answer))
    support_text = " ".join(str(item.get("snippet") or "") for item in citations)
    answer_support = lexical_support_score(question.expected, answer)
    citation_support = lexical_support_score(question.expected, support_text)
    numeric_ok = numeric_expectations_covered(
        question.expected,
        " ".join(part for part in (answer, support_text) if part),
    )
    if question.gold_doc_name:
        accurate = (not refused) and numeric_ok and max(answer_support, citation_support) >= 0.35
        hallucinated = (not refused) and bool(citations) and citation_support < 0.20
    else:
        accurate = refused
        hallucinated = not refused
    return {
        "refused": refused,
        "citation_coverage": citation_coverage,
        "answer_support_score": answer_support,
        "citation_support_score": citation_support,
        "auto_accurate": accurate,
        "auto_hallucinated": hallucinated,
        "manual_accuracy": "",
        "manual_completeness": "",
        "manual_traceability": "",
        "manual_safety": "",
    }


def summarize_answer_scores(scores: list[dict[str, Any]], questions: list[EvalQuestion]) -> dict[str, Any]:
    """汇总 RAG 与直接大模型的自动代理指标。"""

    out_scope_indexes = {index for index, item in enumerate(questions) if not item.gold_doc_name}
    return {
        "answer_accuracy": _safe_div(sum(1 for item in scores if item["auto_accurate"]), len(scores)),
        "citation_coverage_rate": _safe_div(sum(1 for item in scores if item["citation_coverage"]), len(scores)),
        "hallucination_rate": _safe_div(sum(1 for item in scores if item["auto_hallucinated"]), len(scores)),
        "out_of_scope_refusal_rate": _safe_div(
            sum(1 for index, item in enumerate(scores) if index in out_scope_indexes and item["refused"]),
            len(out_scope_indexes),
        ),
        "avg_elapsed_ms": int(
            mean(
                [
                    int(item.get("elapsed_ms") or item.get("retrieve_ms", 0) + item.get("generate_ms", 0))
                    for item in scores
                ]
            )
        )
        if scores
        else 0,
    }


def summarize_retrieval_cases(cases: list[RetrievalCase], topk: int) -> dict[str, Any]:
    """汇总检索类实验指标。"""

    ranks = [item.rank for item in cases]
    non_refused = [item for item in cases if not item.refused]
    return {
        f"recall_at_{topk}": _safe_div(sum(1 for rank in ranks if rank is not None and rank <= topk), len(cases)),
        "mrr": _safe_div(sum(1 / rank for rank in ranks if rank), len(cases)),
        "avg_retrieve_ms": int(mean([item.retrieve_ms for item in cases])) if cases else 0,
        "citation_accuracy": _safe_div(
            sum(1 for item in non_refused if item.citation_accurate),
            len(non_refused),
        ),
        "refusal_rate": _safe_div(sum(1 for item in cases if item.refused), len(cases)),
        "samples": len(cases),
    }


def refusal_reason_for(
    question: str,
    hits: list[VectorHit],
    threshold: float | None,
) -> str | None:
    """按项目拒答策略的核心规则判定是否拒答。"""

    if not hits:
        return "NO_EVIDENCE"
    if threshold is not None and hits[0].score < threshold:
        return "LOW_SCORE"
    context = " ".join(str(hit.payload.get("text") or "") for hit in hits)
    if len(context.strip()) < 20:
        return "LOW_EVIDENCE"
    if keyword_coverage_ratio(question, hits) < 0.30:
        return "LOW_COVERAGE"
    return None


def keyword_coverage_ratio(question: str, hits: list[VectorHit]) -> float:
    """计算问题字符在命中文本中的覆盖率。"""

    tokens = [char.lower() for char in question.strip() if char.strip()]
    if not tokens:
        return 1.0
    content = " ".join(str(hit.payload.get("text") or "") for hit in hits).lower()
    covered = sum(1 for token in tokens if token in content)
    return covered / len(tokens)


def citation_payload(index: int, hit: VectorHit) -> dict[str, Any]:
    """构造实验引用结构。"""

    payload = hit.payload
    return {
        "citation_id": index,
        "doc_name": payload.get("doc_name"),
        "doc_id": payload.get("doc_id"),
        "page_start": payload.get("page_start"),
        "page_end": payload.get("page_end"),
        "section_path": payload.get("section_path"),
        "chunk_id": payload.get("chunk_id"),
        "score": hit.score,
        "snippet": " ".join(str(payload.get("text") or "").split())[:200],
    }


def is_citation_accurate(question: EvalQuestion, citations: list[dict[str, Any]]) -> bool:
    """判断引用是否来自标准文档且片段能支撑 expected。"""

    if not question.gold_doc_name:
        return False
    for item in citations:
        if item.get("doc_name") != question.gold_doc_name:
            continue
        if lexical_support_score(question.expected, str(item.get("snippet") or "")) >= 0.25:
            return True
    return False


def lexical_support_score(expected: str, text: str) -> float:
    """用关键词重合度近似判断证据支撑度。"""

    tokens = important_tokens(expected)
    if not tokens:
        return 0.0
    normalized = re.sub(r"\s+", "", text.lower())
    matched = sum(1 for token in tokens if token in normalized)
    return matched / len(tokens)


def numeric_expectations_covered(expected: str, text: str) -> bool:
    """校验 expected 中的数字、日期和时间是否被回答或证据覆盖。"""

    numbers = re.findall(r"\d+(?:[.:\-/]\d+)*", expected)
    if not numbers:
        return True
    compact_text = re.sub(r"\s+", "", text)
    return all(number in compact_text for number in numbers)


def important_tokens(text: str) -> list[str]:
    """抽取用于自动评分的数字、英文词与中文短语。"""

    normalized = re.sub(r"\s+", "", text.lower())
    tokens = re.findall(r"[a-z0-9]+(?:[.@:/-][a-z0-9]+)*", normalized)
    for size in (4, 3, 2):
        for index in range(0, max(0, len(normalized) - size + 1)):
            token = normalized[index : index + size]
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                tokens.append(token)
    stop = {"什么", "哪些", "多少", "如何", "可以", "需要", "分别", "是什么"}
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in stop or token in seen:
            continue
        seen.add(token)
        deduped.append(token)
        if len(deduped) >= 24:
            break
    return deduped


def looks_like_refusal(answer: str) -> bool:
    """识别回答是否属于拒答。"""

    patterns = (
        "无法给出可靠答案",
        "证据不足",
        "未找到足够证据",
        "无法回答",
        "不能确定",
        "无法确认",
        "没有相关信息",
    )
    return any(pattern in answer for pattern in patterns)


def first_match_rank(hits: list[VectorHit], gold_doc_name: str | None) -> int | None:
    """返回标准文档首次出现的排名。"""

    if not gold_doc_name:
        return None
    for index, hit in enumerate(hits, start=1):
        if hit.payload.get("doc_name") == gold_doc_name:
            return index
    return None


def load_eval_questions(path: Path) -> list[EvalQuestion]:
    """加载评测集。"""

    data = json.loads(path.read_text(encoding="utf-8"))
    questions = []
    for item in data.get("items", []):
        questions.append(
            EvalQuestion(
                question=item["question"],
                expected=item.get("expected") or "",
                question_type=item.get("type") or item.get("question_type") or "未分类",
                gold_doc_name=item.get("gold_doc_name"),
            )
        )
    return questions


def select_llm_questions(questions: list[EvalQuestion], sample_size: int) -> list[EvalQuestion]:
    """选择大模型对比样本，兼顾知识库内外问题。"""

    if sample_size <= 0:
        return []
    out_scope_target = max(1, sample_size // 5)
    in_scope_target = sample_size - out_scope_target
    in_scope = [item for item in questions if item.gold_doc_name][:in_scope_target]
    out_scope = [item for item in questions if not item.gold_doc_name][:out_scope_target]
    selected = [*in_scope, *out_scope]
    if len(selected) < sample_size:
        selected.extend([item for item in questions if item not in selected][: sample_size - len(selected)])
    return selected[:sample_size]


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    """写出可直接用于论文整理的 Markdown 报告。"""

    lines = [
        "# CampusSage 论文补充实验报告",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- Embedding 模型：`{payload['environment']['embedding_model']}`",
        f"- 向量数据库：`{payload['environment']['vector_database']}`",
        f"- 重排策略：`{payload['environment']['reranker']}`",
        "",
        "## 实验一：分块参数对比",
        "",
        "| 组别 | chunk_size | chunk_overlap | chunk 数 | Recall@5 | MRR | 平均检索耗时(ms) | 引用准确率 | 拒答率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["experiment_1_chunk"]:
        lines.append(
            f"| {item['group']} | {item['chunk_size']} | {item['chunk_overlap']} | "
            f"{item['chunk_count']} | {item['recall_at_5']:.4f} | {item['mrr']:.4f} | "
            f"{item['avg_retrieve_ms']} | {item['citation_accuracy']:.4f} | {item['refusal_rate']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 实验二：拒答阈值对比",
            "",
            "| 组别 | threshold | 知识库内拒答率 | 知识库外拒答率 | 错误回答率 | 引用覆盖率 | 平均响应时间(ms) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["experiment_2_threshold"]:
        lines.append(
            f"| {item['group']} | {item['threshold']:.2f} | {item['in_scope_refusal_rate']:.4f} | "
            f"{item['out_of_scope_refusal_rate']:.4f} | {item['wrong_answer_rate']:.4f} | "
            f"{item['citation_coverage_rate']:.4f} | {item['avg_response_ms']} |"
        )
    lines.extend(
        [
            "",
            "## 实验三：重排策略消融",
            "",
            "| 组别 | 是否重排 | Recall@5 | MRR | Top1 命中率 | 平均检索耗时(ms) |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["experiment_3_rerank"]:
        lines.append(
            f"| {item['group']} | {item['rerank_enabled']} | {item['recall_at_5']:.4f} | "
            f"{item['mrr']:.4f} | {item['top1_hit_rate']:.4f} | {item['avg_retrieve_ms']} |"
        )
    lines.append("")
    lines.append("## 实验四：RAG 与直接大模型")
    llm = payload.get("experiment_4_llm")
    if not llm or llm.get("skipped"):
        lines.append("")
        lines.append(f"- 未执行：{(llm or {}).get('reason', '已通过参数跳过')}")
    else:
        lines.extend(
            [
                "",
                "| 方法 | 答案准确率 | 引用覆盖率 | 幻觉率 | 知识库外拒答率 | 平均耗时(ms) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, label in (("direct", "直接大模型"), ("rag", "CampusSage RAG")):
            item = llm[name]
            lines.append(
                f"| {label} | {item['answer_accuracy']:.4f} | {item['citation_coverage_rate']:.4f} | "
                f"{item['hallucination_rate']:.4f} | {item['out_of_scope_refusal_rate']:.4f} | "
                f"{item['avg_elapsed_ms']} |"
            )
        lines.extend(
            [
                "",
                "> 自动评分仅用于预筛，最终论文建议结合 `llm_manual_scoring_sheet.csv` 做人工复核。",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sqlite(path: Path, payload: dict[str, Any]) -> None:
    """把汇总指标同步写入 SQLite，便于后续复核。"""

    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_rows (
                experiment TEXT NOT NULL,
                group_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM metric_rows")
        for item in payload["experiment_1_chunk"]:
            insert_metrics(conn, "chunk", item["group"], item)
        for item in payload["experiment_2_threshold"]:
            insert_metrics(conn, "threshold", item["group"], item)
        for item in payload["experiment_3_rerank"]:
            insert_metrics(conn, "rerank", item["group"], item)
        llm = payload.get("experiment_4_llm")
        if llm and not llm.get("skipped"):
            insert_metrics(conn, "llm", "direct", llm["direct"])
            insert_metrics(conn, "llm", "rag", llm["rag"])
        conn.commit()
    finally:
        conn.close()


def insert_metrics(conn: sqlite3.Connection, experiment: str, group_name: str, row: dict[str, Any]) -> None:
    """写入一组数值指标。"""

    for key, value in row.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            conn.execute(
                "INSERT INTO metric_rows(experiment, group_name, metric_name, metric_value) VALUES (?, ?, ?, ?)",
                (experiment, group_name, key, float(value)),
            )


def write_llm_scoring_sheet(path: Path, llm_results: dict[str, Any] | None) -> None:
    """导出大模型对比人工评分表。"""

    if not llm_results or llm_results.get("skipped"):
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "index",
                "question",
                "expected",
                "method",
                "answer",
                "citations",
                "manual_accuracy",
                "manual_completeness",
                "manual_traceability",
                "manual_safety",
            ],
        )
        writer.writeheader()
        for item in llm_results["items"]:
            for method in ("direct", "rag"):
                detail = item[method]
                writer.writerow(
                    {
                        "index": item["index"],
                        "question": item["question"],
                        "expected": item["expected"],
                        "method": method,
                        "answer": detail["answer"],
                        "citations": json.dumps(detail.get("citations") or [], ensure_ascii=False),
                        "manual_accuracy": "",
                        "manual_completeness": "",
                        "manual_traceability": "",
                        "manual_safety": "",
                    }
                )


def write_json(path: Path, payload: Any) -> None:
    """写出 UTF-8 JSON。"""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _console_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """生成控制台精简摘要。"""

    return {
        "output_dir": payload["output_dir"],
        "chunk": [
            {
                "group": item["group"],
                "recall_at_5": item["recall_at_5"],
                "mrr": item["mrr"],
                "citation_accuracy": item["citation_accuracy"],
                "refusal_rate": item["refusal_rate"],
            }
            for item in payload["experiment_1_chunk"]
        ],
        "threshold": [
            {
                "group": item["group"],
                "threshold": item["threshold"],
                "in_scope_refusal_rate": item["in_scope_refusal_rate"],
                "out_of_scope_refusal_rate": item["out_of_scope_refusal_rate"],
                "wrong_answer_rate": item["wrong_answer_rate"],
            }
            for item in payload["experiment_2_threshold"]
        ],
        "rerank": [
            {
                "rerank_enabled": item["rerank_enabled"],
                "recall_at_5": item["recall_at_5"],
                "mrr": item["mrr"],
                "top1_hit_rate": item["top1_hit_rate"],
            }
            for item in payload["experiment_3_rerank"]
        ],
        "llm_skipped": bool((payload.get("experiment_4_llm") or {}).get("skipped")),
    }


def _default_output_dir() -> Path:
    """构造默认输出目录。"""

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return ROOT_DIR / "outputs" / f"paper_experiments_{timestamp}"


def _resolve_output_dir(path: Path) -> Path:
    """将输出目录规范化到绝对路径。"""

    return path if path.is_absolute() else ROOT_DIR / path


def _batch(items: list[Any], batch_size: int) -> list[list[Any]]:
    """按固定大小切分列表。"""

    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _point_id(chunk_id: str) -> str:
    """把业务 chunk_id 转换为 Qdrant 点 ID。"""

    return str(uuid5(POINT_NAMESPACE, chunk_id))


def _normalize_vectors(value: Any) -> list[list[float]]:
    """把模型输出标准化为二维 float 列表。"""

    if hasattr(value, "tolist"):
        value = value.tolist()
    return [[float(item) for item in vector] for vector in value]


def _safe_div(numerator: float, denominator: float) -> float:
    """安全除法。"""

    return float(numerator / denominator) if denominator else 0.0


if __name__ == "__main__":
    main()
