from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.settings import Settings
from app.core.utils import new_id
from app.db.database import get_database
from app.db.models import MessageRecord
from app.db.repos.conversation import ConversationRepository
from app.db.repos.interfaces import KnowledgeBaseRepositoryProtocol
from app.rag.context_builder import ContextBuilder
from app.rag.conversation_service import ConversationService
from app.rag.dto import AskResult, CitationDTO
from app.rag.embedding import Embedder, get_embedder
from app.rag.llm_client import VllmClient
from app.rag.reranker import SimpleReranker
from app.rag.vector_store import VectorHit, VectorStore, get_vector_store


@dataclass(slots=True)
class _ComputationResult:
    """问答计算中间结果。"""

    answer: str
    refusal: bool
    refusal_reason: str | None
    suggestions: list[str]
    citations: list[CitationDTO]
    timing: dict[str, int]
    topk: int
    threshold: float
    rerank_enabled: bool
    hits_for_log: list[VectorHit]


class RagService:
    """问答服务。"""

    def __init__(self, kb_repo: KnowledgeBaseRepositoryProtocol, settings: Settings) -> None:
        self._kb_repo = kb_repo
        self._settings = settings
        self._embedder: Embedder = get_embedder(settings)
        self._vector_store: VectorStore = get_vector_store(settings)
        self._context_builder = ContextBuilder(settings.rag_max_context_tokens)
        self._llm_client = VllmClient(settings)
        self._reranker = SimpleReranker()
        self._logger = get_logger()
        database = get_database(settings)
        repository = ConversationRepository(database)
        self._conversation_service = ConversationService(repository)

    def ask(
        self,
        kb_id: str,
        question: str,
        request_id: str | None,
        conversation_id: str | None,
        user_id: str | None,
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
        filters: dict[str, object] | None,
        debug: bool,
    ) -> AskResult:
        """发起问答。"""

        kb = self._get_kb(kb_id)
        conversation = self._conversation_service.ensure_conversation(
            kb_id=kb_id,
            conversation_id=conversation_id,
            title=question.strip()[:50] if question.strip() else None,
            user_id=user_id,
        )
        computed = self._compute_answer(
            kb=kb,
            question=question,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
            filters=filters,
            debug=debug,
        )
        user_message = self._save_user_message(
            conversation_id=conversation.conversation_id,
            question=question,
        )
        assistant_message = self._save_assistant_message(
            conversation_id=conversation.conversation_id,
            computed=computed,
            parent_message_id=user_message.message_id,
        )
        result = AskResult(
            answer=computed.answer,
            refusal=computed.refusal,
            refusal_reason=computed.refusal_reason,
            suggestions=computed.suggestions,
            citations=computed.citations,
            conversation_id=conversation.conversation_id,
            message_id=assistant_message.message_id,
            user_message_id=user_message.message_id,
            assistant_created_at=assistant_message.created_at,
            timing=computed.timing,
            request_id=request_id,
        )
        self._log_ask(
            request_id=request_id,
            kb_id=kb_id,
            topk=computed.topk,
            threshold=computed.threshold,
            rerank_enabled=computed.rerank_enabled,
            retrieve_ms=computed.timing["retrieve_ms"],
            rerank_ms=computed.timing["rerank_ms"],
            context_ms=computed.timing["context_ms"],
            generate_ms=computed.timing["generate_ms"],
            total_ms=computed.timing["total_ms"],
            hits=computed.hits_for_log,
            refusal_reason=computed.refusal_reason,
        )
        return result

    def ask_for_existing_user_message(
        self,
        kb_id: str,
        question: str,
        request_id: str | None,
        conversation_id: str,
        user_message_id: str,
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
        filters: dict[str, object] | None,
        debug: bool,
    ) -> AskResult:
        """基于已存在用户消息生成新回答。"""

        kb = self._get_kb(kb_id)
        computed = self._compute_answer(
            kb=kb,
            question=question,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
            filters=filters,
            debug=debug,
        )
        assistant_message = self._save_assistant_message(
            conversation_id=conversation_id,
            computed=computed,
            parent_message_id=user_message_id,
        )
        result = AskResult(
            answer=computed.answer,
            refusal=computed.refusal,
            refusal_reason=computed.refusal_reason,
            suggestions=computed.suggestions,
            citations=computed.citations,
            conversation_id=conversation_id,
            message_id=assistant_message.message_id,
            user_message_id=user_message_id,
            assistant_created_at=assistant_message.created_at,
            timing=computed.timing,
            request_id=request_id,
        )
        self._log_ask(
            request_id=request_id,
            kb_id=kb_id,
            topk=computed.topk,
            threshold=computed.threshold,
            rerank_enabled=computed.rerank_enabled,
            retrieve_ms=computed.timing["retrieve_ms"],
            rerank_ms=computed.timing["rerank_ms"],
            context_ms=computed.timing["context_ms"],
            generate_ms=computed.timing["generate_ms"],
            total_ms=computed.timing["total_ms"],
            hits=computed.hits_for_log,
            refusal_reason=computed.refusal_reason,
        )
        return result

    def ask_stream(
        self,
        kb_id: str,
        question: str,
        request_id: str | None,
        conversation_id: str | None,
        user_id: str | None,
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
        filters: dict[str, object] | None,
        debug: bool,
        run_id: str,
        cancel_checker: Callable[[], bool],
    ) -> Iterator[dict[str, object]]:
        """流式问答。"""

        kb = self._get_kb(kb_id)
        conversation = self._conversation_service.ensure_conversation(
            kb_id=kb_id,
            conversation_id=conversation_id,
            title=question.strip()[:50] if question.strip() else None,
            user_id=user_id,
        )
        yield {
            "event": "start",
            "data": {
                "run_id": run_id,
                "conversation_id": conversation.conversation_id,
                "request_id": request_id,
            },
        }
        if cancel_checker():
            yield self._canceled_event(run_id, request_id)
            yield self._done_event(run_id, request_id, status="canceled")
            return
        user_message = self._save_user_message(
            conversation_id=conversation.conversation_id,
            question=question,
        )
        if cancel_checker():
            yield self._canceled_event(run_id, request_id, user_message.message_id)
            yield self._done_event(
                run_id,
                request_id,
                status="canceled",
                conversation_id=conversation.conversation_id,
                user_message_id=user_message.message_id,
            )
            return
        computed = self._compute_answer(
            kb=kb,
            question=question,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
            filters=filters,
            debug=debug,
        )
        if computed.refusal:
            assistant_message = self._save_assistant_message(
                conversation_id=conversation.conversation_id,
                computed=computed,
                parent_message_id=user_message.message_id,
            )
            self._log_ask(
                request_id=request_id,
                kb_id=kb_id,
                topk=computed.topk,
                threshold=computed.threshold,
                rerank_enabled=computed.rerank_enabled,
                retrieve_ms=computed.timing["retrieve_ms"],
                rerank_ms=computed.timing["rerank_ms"],
                context_ms=computed.timing["context_ms"],
                generate_ms=computed.timing["generate_ms"],
                total_ms=computed.timing["total_ms"],
                hits=computed.hits_for_log,
                refusal_reason=computed.refusal_reason,
            )
            yield {
                "event": "refusal",
                "data": {
                    "run_id": run_id,
                    "answer": computed.answer,
                    "refusal_reason": computed.refusal_reason,
                    "suggestions": computed.suggestions,
                    "conversation_id": conversation.conversation_id,
                    "user_message_id": user_message.message_id,
                    "message_id": assistant_message.message_id,
                    "assistant_created_at": assistant_message.created_at,
                    "timing": computed.timing,
                    "request_id": request_id,
                },
            }
            yield self._done_event(
                run_id,
                request_id,
                status="succeeded",
                conversation_id=conversation.conversation_id,
                user_message_id=user_message.message_id,
                assistant_message_id=assistant_message.message_id,
                assistant_created_at=assistant_message.created_at,
                refusal=True,
            )
            return
        for chunk in self._stream_text_chunks(computed.answer):
            if cancel_checker():
                yield self._canceled_event(run_id, request_id, user_message.message_id)
                yield self._done_event(
                    run_id,
                    request_id,
                    status="canceled",
                    conversation_id=conversation.conversation_id,
                    user_message_id=user_message.message_id,
                )
                return
            yield {
                "event": "token",
                "data": {
                    "run_id": run_id,
                    "delta": chunk,
                    "request_id": request_id,
                },
            }
        assistant_message = self._save_assistant_message(
            conversation_id=conversation.conversation_id,
            computed=computed,
            parent_message_id=user_message.message_id,
        )
        for citation in computed.citations:
            yield {
                "event": "citation",
                "data": {
                    "run_id": run_id,
                    "citation": citation.model_dump(),
                    "request_id": request_id,
                },
            }
        self._log_ask(
            request_id=request_id,
            kb_id=kb_id,
            topk=computed.topk,
            threshold=computed.threshold,
            rerank_enabled=computed.rerank_enabled,
            retrieve_ms=computed.timing["retrieve_ms"],
            rerank_ms=computed.timing["rerank_ms"],
            context_ms=computed.timing["context_ms"],
            generate_ms=computed.timing["generate_ms"],
            total_ms=computed.timing["total_ms"],
            hits=computed.hits_for_log,
            refusal_reason=None,
        )
        yield self._done_event(
            run_id,
            request_id,
            status="succeeded",
            conversation_id=conversation.conversation_id,
            user_message_id=user_message.message_id,
            assistant_message_id=assistant_message.message_id,
            assistant_created_at=assistant_message.created_at,
            refusal=False,
            timing=computed.timing,
        )

    def _compute_answer(
        self,
        kb,
        question: str,
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
        filters: dict[str, object] | None,
        debug: bool,
    ) -> _ComputationResult:
        """执行检索与生成计算。"""

        resolved_topk, resolved_threshold, resolved_rerank_enabled = self._resolve_qa_config(
            kb=kb,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
        )
        min_chunks = kb.config.get("min_evidence_chunks")
        if min_chunks is None:
            min_chunks = self._settings.rag_min_evidence_chunks
        min_context_chars = kb.config.get("min_context_chars")
        if min_context_chars is None:
            min_context_chars = self._settings.rag_min_context_chars
        min_coverage = kb.config.get("min_keyword_coverage")
        if min_coverage is None:
            min_coverage = self._settings.rag_min_keyword_coverage

        total_start = time.perf_counter()
        query_vector = self._embedder.embed_query(question)
        retrieve_start = time.perf_counter()
        hits = self._vector_store.search(
            kb_id=kb.kb_id,
            query_vector=query_vector,
            topk=resolved_topk,
            filters=filters,
        )
        retrieve_ms = int((time.perf_counter() - retrieve_start) * 1000)
        refusal_reason = self._get_refusal_reason(
            question, hits, resolved_threshold, min_chunks, min_coverage
        )
        if refusal_reason is not None:
            total_ms = int((time.perf_counter() - total_start) * 1000)
            return _ComputationResult(
                answer="当前知识库中未找到足够证据，无法给出可靠答案。",
                refusal=True,
                refusal_reason=refusal_reason,
                suggestions=[
                    "建议到教务处官网查询相关规定",
                    f"建议关键词：{question} 条件",
                ],
                citations=[],
                timing={
                    "retrieve_ms": retrieve_ms,
                    "rerank_ms": 0,
                    "context_ms": 0,
                    "generate_ms": 0,
                    "total_ms": total_ms,
                },
                topk=resolved_topk,
                threshold=resolved_threshold,
                rerank_enabled=resolved_rerank_enabled,
                hits_for_log=hits,
            )

        rerank_ms = 0
        if resolved_rerank_enabled:
            rerank_start = time.perf_counter()
            hits = self._reranker.rerank(question, hits)
            rerank_ms = int((time.perf_counter() - rerank_start) * 1000)

        context_start = time.perf_counter()
        context_result = self._context_builder.build(hits)
        context_ms = int((time.perf_counter() - context_start) * 1000)
        if not context_result.hits or len(context_result.context.strip()) < min_context_chars:
            total_ms = int((time.perf_counter() - total_start) * 1000)
            return _ComputationResult(
                answer="当前知识库中未找到足够证据，无法给出可靠答案。",
                refusal=True,
                refusal_reason="LOW_EVIDENCE",
                suggestions=[
                    "建议到教务处官网查询相关规定",
                    f"建议关键词：{question} 条件",
                ],
                citations=[],
                timing={
                    "retrieve_ms": retrieve_ms,
                    "rerank_ms": rerank_ms,
                    "context_ms": context_ms,
                    "generate_ms": 0,
                    "total_ms": total_ms,
                },
                topk=resolved_topk,
                threshold=resolved_threshold,
                rerank_enabled=resolved_rerank_enabled,
                hits_for_log=context_result.hits,
            )

        citations = self._build_citations(context_result.hits, debug)
        generate_start = time.perf_counter()
        if self._settings.vllm_enabled:
            answer = self._llm_client.generate(question=question, context=context_result.context)
            answer = self._ensure_citations_in_answer(answer, citations)
        else:
            answer = self._build_answer(citations)
        generate_ms = int((time.perf_counter() - generate_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        return _ComputationResult(
            answer=answer,
            refusal=False,
            refusal_reason=None,
            suggestions=[],
            citations=citations,
            timing={
                "retrieve_ms": retrieve_ms,
                "rerank_ms": rerank_ms,
                "context_ms": context_ms,
                "generate_ms": generate_ms,
                "total_ms": total_ms,
            },
            topk=resolved_topk,
            threshold=resolved_threshold,
            rerank_enabled=resolved_rerank_enabled,
            hits_for_log=context_result.hits,
        )

    def _resolve_qa_config(
        self,
        kb,
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
    ) -> tuple[int, float, bool]:
        """解析问答配置。"""

        resolved_topk = topk or kb.config.get("topk", self._settings.rag_topk)
        resolved_threshold = threshold if threshold is not None else kb.config.get(
            "threshold", self._settings.rag_threshold
        )
        resolved_rerank_enabled = (
            rerank_enabled
            if rerank_enabled is not None
            else kb.config.get("rerank_enabled", self._settings.rerank_enabled)
        )
        return int(resolved_topk), float(resolved_threshold), bool(resolved_rerank_enabled)

    def _get_kb(self, kb_id: str):
        """获取知识库记录。"""

        kb = self._kb_repo.get(kb_id)
        if kb is None or kb.deleted:
            raise AppError(
                code=ErrorCode.KB_NOT_FOUND,
                message="知识库不存在",
                detail={"kb_id": kb_id},
                status_code=404,
            )
        return kb

    def _save_user_message(self, conversation_id: str, question: str) -> MessageRecord:
        """保存用户消息。"""

        return self._conversation_service.save_message(
            conversation_id=conversation_id,
            role="user",
            content=question,
            refusal=False,
            refusal_reason=None,
            timing=None,
            citations=None,
        )

    def _save_assistant_message(
        self,
        conversation_id: str,
        computed: _ComputationResult,
        parent_message_id: str | None,
    ) -> MessageRecord:
        """保存助手消息。"""

        return self._conversation_service.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=computed.answer,
            refusal=computed.refusal,
            refusal_reason=computed.refusal_reason,
            timing=computed.timing,
            citations=[item.model_dump() for item in computed.citations],
            message_id=new_id("msg"),
            parent_message_id=parent_message_id,
        )

    def _stream_text_chunks(self, text: str, chunk_size: int = 24) -> Iterator[str]:
        """将文本切分为流式片段。"""

        if not text:
            yield ""
            return
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def _canceled_event(
        self, run_id: str, request_id: str | None, user_message_id: str | None = None
    ) -> dict[str, object]:
        """构造取消事件。"""

        return {
            "event": "error",
            "data": {
                "run_id": run_id,
                "code": ErrorCode.CHAT_RUN_CANCELED.value,
                "message": "生成已取消",
                "user_message_id": user_message_id,
                "request_id": request_id,
            },
        }

    def _done_event(
        self,
        run_id: str,
        request_id: str | None,
        status: str,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
        assistant_created_at: str | None = None,
        refusal: bool | None = None,
        timing: dict[str, int] | None = None,
    ) -> dict[str, object]:
        """构造完成事件。"""

        return {
            "event": "done",
            "data": {
                "run_id": run_id,
                "status": status,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "message_id": assistant_message_id,
                "assistant_created_at": assistant_created_at,
                "refusal": refusal,
                "timing": timing,
                "request_id": request_id,
            },
        }

    def _get_refusal_reason(
        self,
        question: str,
        hits: list[VectorHit],
        threshold: float,
        min_chunks: int,
        min_coverage: float,
    ) -> str | None:
        """判断是否需要拒答并返回原因码。"""

        if not hits:
            return "NO_EVIDENCE"
        if hits[0].score < threshold:
            return "LOW_SCORE"
        if len(hits) < min_chunks:
            return "LOW_EVIDENCE"
        if self._keyword_coverage_ratio(question, hits) < min_coverage:
            return "LOW_COVERAGE"
        return None

    def _build_citations(self, hits: list[VectorHit], debug: bool) -> list[CitationDTO]:
        """构建引用列表。"""

        citations = []
        for index, hit in enumerate(hits, start=1):
            payload = hit.payload
            citations.append(
                CitationDTO(
                    citation_id=index,
                    doc_id=payload.get("doc_id"),
                    doc_name=payload.get("doc_name"),
                    doc_version=payload.get("doc_version"),
                    published_at=payload.get("published_at"),
                    page_start=payload.get("page_start"),
                    page_end=payload.get("page_end"),
                    section_path=payload.get("section_path"),
                    chunk_id=payload.get("chunk_id"),
                    snippet=self._build_snippet(payload.get("text", "")),
                    score=hit.score if debug else None,
                )
            )
        return citations

    def _build_snippet(self, text: str) -> str:
        """生成引用片段。"""

        limit = self._settings.rag_max_snippet_chars
        cleaned = " ".join(text.strip().split())
        return cleaned[:limit]

    def _build_answer(self, citations: list[CitationDTO]) -> str:
        """构建答案文本。"""

        if not citations:
            return "未找到可用证据。"
        head = citations[0].snippet
        return f"根据检索到的证据，相关内容如下：[1] {head}"

    def _ensure_citations_in_answer(
        self, answer: str, citations: list[CitationDTO]
    ) -> str:
        """确保答案中包含引用编号。"""

        if not citations:
            return answer
        content = answer.strip()
        if not content:
            return self._build_answer(citations)
        if re.search(r"\[\d+\]", content):
            return content
        markers = "".join(f"[{item.citation_id}]" for item in citations)
        return f"{content}\n\n参考：{markers}"

    def _keyword_coverage_ratio(self, question: str, hits: list[VectorHit]) -> float:
        """计算问题关键词在命中文本中的覆盖率。"""

        tokens = {token for token in self._tokenize_question(question) if token.strip()}
        if not tokens:
            return 1.0
        content = " ".join((hit.payload.get("text") or "") for hit in hits).lower()
        if not content:
            return 0.0
        covered = sum(1 for token in tokens if token.lower() in content)
        return covered / max(1, len(tokens))

    def _tokenize_question(self, question: str) -> list[str]:
        """拆分问题关键词（中文以字符兜底）。"""

        stripped = question.strip()
        if not stripped:
            return []
        tokens = stripped.split()
        if len(tokens) > 1:
            return [token.lower() for token in tokens]
        if tokens and len(tokens[0]) <= 2:
            return [tokens[0].lower()]
        return [char.lower() for char in stripped if char.strip()]

    def _log_ask(
        self,
        request_id: str | None,
        kb_id: str,
        topk: int,
        threshold: float,
        rerank_enabled: bool,
        retrieve_ms: int,
        rerank_ms: int,
        context_ms: int,
        generate_ms: int,
        total_ms: int,
        hits: list[VectorHit],
        refusal_reason: str | None,
    ) -> None:
        """记录问答关键日志。"""

        doc_ids = {hit.payload.get("doc_id") for hit in hits if hit.payload.get("doc_id")}
        log_event(
            self._logger,
            event="rag",
            fields={
                "request_id": request_id,
                "kb_id": kb_id,
                "topk": topk,
                "threshold": threshold,
                "rerank_enabled": rerank_enabled,
                "retrieve_ms": retrieve_ms,
                "rerank_ms": rerank_ms,
                "context_ms": context_ms,
                "generate_ms": generate_ms,
                "total_ms": total_ms,
                "hit_docs": len(doc_ids),
                "hit_chunks": len(hits),
                "refusal_reason": refusal_reason,
            },
        )
