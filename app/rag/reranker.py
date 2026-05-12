from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.rag.vector_store import VectorHit


class Reranker(Protocol):
    """重排器接口，便于在启发式、本地模型和 HTTP 模型之间切换。"""

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]: ...


class SimpleReranker:
    """简单重排器，融合短语命中、标题命中与向量分数。"""

    _MAX_QUERY_PHRASES = 16
    _MAX_MATCHED_PHRASES = 6
    _NOISE_PHRASES = {
        "是什么",
        "什么",
        "哪些",
        "哪个",
        "如何",
        "怎么",
        "请问",
        "一下",
        "一般",
        "通常",
    }
    _DOMAIN_PHRASES = (
        "主要功能",
        "参与方式",
        "培训对象",
        "开课时间",
        "开课主题",
        "课程安排",
        "课程亮点",
        "第二课堂",
        "科学导航",
        "知识库",
    )

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """根据问句短语覆盖度与标题命中情况重新排序。"""

        if not hits:
            return hits
        normalized_question = self._normalize_text(question)
        if not normalized_question:
            return hits
        query_phrases = self._build_query_phrases(normalized_question)
        return sorted(
            hits,
            key=lambda item: self._sort_key(
                normalized_question=normalized_question,
                query_phrases=query_phrases,
                hit=item,
            ),
            reverse=True,
        )

    def _sort_key(
        self,
        normalized_question: str,
        query_phrases: list[str],
        hit: VectorHit,
    ) -> tuple[int, float, float]:
        """构建重排排序键，优先比较词法相关性，再比较向量分数。"""

        content = self._normalize_text(str(hit.payload.get("text") or ""))
        title = self._normalize_text(
            " ".join(
                str(value)
                for value in (
                    hit.payload.get("doc_name"),
                    hit.payload.get("section_path"),
                )
                if value
            )
        )
        lexical_score = self._lexical_score(
            normalized_question=normalized_question,
            query_phrases=query_phrases,
            content=content,
            title=title,
        )
        domain_coverage = self._domain_phrase_coverage(
            normalized_question=normalized_question,
            content=content,
            title=title,
        )
        return domain_coverage, lexical_score, hit.score

    def _lexical_score(
        self,
        normalized_question: str,
        query_phrases: list[str],
        content: str,
        title: str,
    ) -> float:
        """计算融合短语、标题与正文命中的启发式分数。"""

        score = 0.0
        compact_question = normalized_question.replace(" ", "")
        compact_content = content.replace(" ", "")
        compact_title = title.replace(" ", "")

        if compact_question and compact_question in compact_content:
            score += 20.0
        if compact_question and compact_question in compact_title:
            score += 14.0
        score += self._domain_phrase_bonus(compact_question, compact_content, compact_title)
        score += self._phrase_score(query_phrases, compact_content, title_match=False)
        score += self._phrase_score(query_phrases, compact_title, title_match=True)
        return score

    def _domain_phrase_bonus(
        self,
        compact_question: str,
        compact_content: str,
        compact_title: str,
    ) -> float:
        """对通知类常见意图词给额外权重，避免章节命中被向量分数压过。"""

        score = 0.0
        for phrase in self._DOMAIN_PHRASES:
            if phrase not in compact_question:
                continue
            if phrase in compact_title:
                score += 12.0
            if phrase in compact_content:
                score += 6.0
            if phrase not in compact_title and phrase not in compact_content:
                score -= 10.0
        return score

    def _domain_phrase_coverage(
        self,
        normalized_question: str,
        content: str,
        title: str,
    ) -> int:
        """统计问句中的领域短语被候选命中的数量，用作强排序特征。"""

        compact_question = normalized_question.replace(" ", "")
        compact_content = content.replace(" ", "")
        compact_title = title.replace(" ", "")
        coverage = 0
        for phrase in self._DOMAIN_PHRASES:
            if phrase not in compact_question:
                continue
            if phrase in compact_content or phrase in compact_title:
                coverage += 1
        return coverage

    def _phrase_score(
        self, query_phrases: list[str], target: str, title_match: bool
    ) -> float:
        """统计查询短语在目标文本中的命中得分。"""

        matched = [phrase for phrase in query_phrases if phrase in target]
        if not matched:
            return 0.0
        ranked = sorted(set(matched), key=lambda item: (-len(item), query_phrases.index(item)))
        score = 0.0
        for index, phrase in enumerate(ranked[: self._MAX_MATCHED_PHRASES]):
            base = self._phrase_weight(len(phrase))
            if title_match:
                base *= 1.25
            # 对后续短语逐步衰减，避免重叠 ngram 叠分过高。
            score += base / (1 + index * 0.35)
        return score

    def _build_query_phrases(self, normalized_question: str) -> list[str]:
        """从问句中提取可用于重排的关键短语。"""

        phrases: list[str] = []
        seen: set[str] = set()
        compact_question = normalized_question.replace(" ", "")
        for phrase in self._DOMAIN_PHRASES:
            if phrase in compact_question:
                self._append_phrase(phrases, seen, phrase)
        for token in normalized_question.split():
            self._append_phrase(phrases, seen, token)

        if len(phrases) < self._MAX_QUERY_PHRASES and compact_question:
            for size in (5, 4, 3, 2):
                if len(compact_question) < size:
                    continue
                for index in range(0, len(compact_question) - size + 1):
                    self._append_phrase(
                        phrases,
                        seen,
                        compact_question[index : index + size],
                    )
                    if len(phrases) >= self._MAX_QUERY_PHRASES:
                        break
                if len(phrases) >= self._MAX_QUERY_PHRASES:
                    break
        if compact_question and len(compact_question) <= 12:
            self._append_phrase(phrases, seen, compact_question)
        return phrases

    def _append_phrase(
        self,
        phrases: list[str],
        seen: set[str],
        phrase: str,
    ) -> None:
        """向短语列表追加一个合法短语。"""

        candidate = phrase.strip()
        if not candidate or candidate in seen:
            return
        if len(candidate) < 2:
            return
        if candidate in self._NOISE_PHRASES:
            return
        if self._is_noise_phrase(candidate):
            return
        seen.add(candidate)
        phrases.append(candidate)

    def _is_noise_phrase(self, phrase: str) -> bool:
        """判断短语是否缺少区分度，避免进入重排特征。"""

        if phrase.isdigit():
            return True
        return len(set(phrase)) == 1

    def _normalize_text(self, text: str) -> str:
        """统一清洗文本，降低标点和大小写对匹配的影响。"""

        lowered = text.lower()
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered)
        return " ".join(normalized.split())

    def _phrase_weight(self, phrase_length: int) -> float:
        """根据短语长度分配基础权重。"""

        if phrase_length >= 5:
            return 7.0
        if phrase_length == 4:
            return 5.0
        if phrase_length == 3:
            return 3.0
        return 1.4


class LocalCrossEncoderReranker:
    """基于 sentence-transformers CrossEncoder 的本地模型重排器。"""

    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.rerank_model_name
        self._batch_size = max(1, settings.rerank_batch_size)
        self._model: Any | None = None

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """调用本地 cross-encoder 计算 query-document 相关性。"""

        normalized_question = question.strip()
        if not hits or not normalized_question:
            return hits
        texts = [_build_rerank_text(hit) for hit in hits]
        if not all(text.strip() for text in texts):
            return SimpleReranker().rerank(question, hits)
        pairs = [[normalized_question, text] for text in texts]
        model = self._load_model()
        try:
            raw_scores = model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="本地重排模型推理失败",
                detail={"model": self._model_name, "error": str(exc)},
                status_code=500,
            ) from exc
        return _sort_hits_by_scores(hits, _normalize_scores(raw_scores))

    def _load_model(self) -> Any:
        """惰性加载本地重排模型，避免进程启动时阻塞。"""

        if self._model is not None:
            return self._model
        cross_encoder_cls = self._load_cross_encoder_cls()
        try:
            self._model = cross_encoder_cls(self._model_name)
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="加载本地重排模型失败",
                detail={"model": self._model_name, "error": str(exc)},
                status_code=500,
            ) from exc
        return self._model

    @staticmethod
    def _load_cross_encoder_cls() -> Any:
        """动态导入 CrossEncoder，便于未启用本地重排时不加载依赖。"""

        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="本地重排依赖缺失，请安装 sentence-transformers",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc
        return CrossEncoder


class HttpReranker:
    """调用 HTTP rerank 服务的模型重排器，兼容常见 /rerank 响应结构。"""

    def __init__(self, settings: Settings) -> None:
        self._endpoint = _build_rerank_endpoint(
            settings.rerank_base_url,
            settings.rerank_api_path,
        )
        self._model = settings.rerank_model_name
        self._timeout = settings.rerank_timeout_s
        self._api_key = settings.rerank_api_key
        self._batch_size = max(1, settings.rerank_batch_size)

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """调用 HTTP 重排服务并按返回分数排序候选证据。"""

        normalized_question = question.strip()
        if not hits or not normalized_question:
            return hits
        texts = [_build_rerank_text(hit) for hit in hits]
        if not any(text.strip() for text in texts):
            return hits
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        scores: list[float | None] = []
        for batch in _iter_batches(texts, self._batch_size):
            scores.extend(self._request_scores(normalized_question, batch, headers))
        if not scores:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="HTTP 重排服务未返回可用分数",
                detail={"endpoint": self._endpoint},
                status_code=502,
            )
        return _sort_hits_by_scores(hits, scores)

    def _request_scores(
        self,
        question: str,
        texts: list[str],
        headers: dict[str, str],
    ) -> list[float | None]:
        """按单批文本调用 HTTP 重排服务。"""

        payload = {
            "model": self._model,
            "query": question,
            "texts": texts,
            "return_documents": False,
        }
        try:
            response = httpx.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=self._timeout,
                trust_env=False,
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="HTTP 重排服务不可用",
                detail={"endpoint": self._endpoint, "error": str(exc)},
                status_code=502,
            ) from exc
        if response.status_code != 200:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="HTTP 重排服务返回异常状态",
                detail={
                    "endpoint": self._endpoint,
                    "status_code": response.status_code,
                    "body": _extract_response_body(response),
                },
                status_code=502,
            )
        scores = _parse_http_scores(response.json())
        if not scores:
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="HTTP 重排服务未返回可用分数",
                detail={"endpoint": self._endpoint, "response": response.json()},
                status_code=502,
            )
        return scores


class FallbackReranker:
    """模型重排失败时回退到启发式重排，保证问答链路可演示。"""

    def __init__(self, primary: Reranker, fallback_enabled: bool) -> None:
        self._primary = primary
        self._fallback = SimpleReranker()
        self._fallback_enabled = fallback_enabled

    def rerank(self, question: str, hits: list[VectorHit]) -> list[VectorHit]:
        """优先执行模型重排，失败时按配置回退或抛出错误。"""

        try:
            return self._primary.rerank(question, hits)
        except AppError:
            if self._fallback_enabled:
                return self._fallback.rerank(question, hits)
            raise
        except Exception as exc:
            if self._fallback_enabled:
                return self._fallback.rerank(question, hits)
            raise AppError(
                code=ErrorCode.RERANK_FAILED,
                message="重排模型执行失败",
                detail={"error": str(exc)},
                status_code=500,
            ) from exc


_reranker: Reranker | None = None
_reranker_key: tuple[object, ...] | None = None


def get_reranker(settings: Settings) -> Reranker:
    """按配置获取重排器实例。"""

    global _reranker, _reranker_key
    key = _build_reranker_key(settings)
    if _reranker is None or _reranker_key != key:
        if settings.rerank_backend == "local":
            _reranker = FallbackReranker(
                LocalCrossEncoderReranker(settings),
                fallback_enabled=settings.rerank_fallback_enabled,
            )
        elif settings.rerank_backend == "http":
            _reranker = FallbackReranker(
                HttpReranker(settings),
                fallback_enabled=settings.rerank_fallback_enabled,
            )
        else:
            _reranker = SimpleReranker()
        _reranker_key = key
    return _reranker


def reset_reranker() -> None:
    """重置重排器实例，供测试或配置切换后重建使用。"""

    global _reranker, _reranker_key
    _reranker = None
    _reranker_key = None


def _build_reranker_key(settings: Settings) -> tuple[object, ...]:
    """提取影响重排器实例化的配置键。"""

    return (
        settings.rerank_backend,
        settings.rerank_model_name,
        settings.rerank_base_url,
        settings.rerank_api_path,
        settings.rerank_timeout_s,
        settings.rerank_api_key,
        settings.rerank_batch_size,
        settings.rerank_fallback_enabled,
    )


def _build_rerank_text(hit: VectorHit) -> str:
    """将候选证据组装为模型可读文本。"""

    payload = hit.payload
    parts = [
        str(payload.get("doc_name") or "").strip(),
        str(payload.get("section_path") or "").strip(),
        str(payload.get("text") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _sort_hits_by_scores(hits: list[VectorHit], scores: list[float | None]) -> list[VectorHit]:
    """按模型分数排序，缺失分数的候选保留在后面并按向量分数兜底。"""

    indexed = list(enumerate(hits))
    return [
        hit
        for index, hit in sorted(
            indexed,
            key=lambda item: _score_sort_key(item[0], item[1], scores),
            reverse=True,
        )
    ]


def _score_sort_key(
    index: int,
    hit: VectorHit,
    scores: list[float | None],
) -> tuple[bool, float, float, int]:
    """构造模型分数排序键。"""

    score = scores[index] if index < len(scores) else None
    if score is None:
        return False, 0.0, hit.score, -index
    return True, score, hit.score, -index


def _normalize_scores(value: Any) -> list[float | None]:
    """把本地模型输出标准化为分数列表。"""

    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (int, float)):
        return [float(value)]
    if not isinstance(value, list):
        raise AppError(
            code=ErrorCode.RERANK_FAILED,
            message="本地重排模型返回格式异常",
            detail={"value_type": type(value).__name__},
            status_code=500,
        )
    scores: list[float | None] = []
    for item in value:
        if isinstance(item, list):
            item = item[0] if item else None
        scores.append(float(item) if isinstance(item, (int, float)) else None)
    return scores


def _iter_batches(items: list[str], batch_size: int) -> list[list[str]]:
    """按固定大小拆分重排候选，避免超过模型服务批量上限。"""

    normalized_batch_size = max(1, batch_size)
    return [
        items[index : index + normalized_batch_size]
        for index in range(0, len(items), normalized_batch_size)
    ]


def _parse_http_scores(data: object) -> list[float | None]:
    """解析 TEI、Cohere/Jina 风格的 HTTP 重排响应。"""

    items: object
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("results") or data.get("data") or data.get("scores")
    else:
        items = None
    if not isinstance(items, list):
        return []
    if all(isinstance(item, (int, float)) for item in items):
        return [float(item) for item in items]

    scores_by_index: dict[int, float] = {}
    for fallback_index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        index_value = item.get("index", item.get("document_index", fallback_index))
        score_value = item.get("score", item.get("relevance_score"))
        if not isinstance(index_value, int) or not isinstance(score_value, (int, float)):
            continue
        scores_by_index[index_value] = float(score_value)
    if not scores_by_index:
        return []
    max_index = max(scores_by_index)
    return [scores_by_index.get(index) for index in range(max_index + 1)]


def _build_rerank_endpoint(base_url: str, api_path: str) -> str:
    """拼接 HTTP 重排请求地址。"""

    normalized_base = base_url.rstrip("/")
    normalized_path = api_path.strip() or "/rerank"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{normalized_base}{normalized_path}"


def _extract_response_body(response: httpx.Response) -> object:
    """提取错误响应体，优先返回 JSON 结构。"""

    try:
        return response.json()
    except Exception:
        return response.text
