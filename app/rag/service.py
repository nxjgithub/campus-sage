from __future__ import annotations

import time

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.settings import Settings
from app.core.utils import new_id
from app.rag.context_builder import ContextBuilder
from app.rag.dto import AskResult, CitationDTO
from app.rag.embedding import SimpleEmbedder
from app.rag.llm_client import VllmClient
from app.db.repos.conversation import ConversationRepository
from app.db.database import get_database
from app.db.repos.interfaces import KnowledgeBaseRepositoryProtocol
from app.rag.conversation_service import ConversationService
from app.rag.reranker import SimpleReranker
from app.rag.vector_store import VectorHit, VectorStore, get_vector_store


class RagService:
    """问答服务（MVP 阶段先返回拒答，避免无证据生成）。"""

    def __init__(self, kb_repo: KnowledgeBaseRepositoryProtocol, settings: Settings) -> None:
        self._kb_repo = kb_repo
        self._settings = settings
        self._embedder = SimpleEmbedder(settings.vector_dim)
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
        topk: int | None,
        threshold: float | None,
        rerank_enabled: bool | None,
        filters: dict[str, object] | None,
        debug: bool,
    ) -> AskResult:
        """发起问答并返回拒答结果。"""

        kb = self._kb_repo.get(kb_id)
        if kb is None or kb.deleted:
            raise AppError(
                code=ErrorCode.KB_NOT_FOUND,
                message="知识库不存在",
                detail={"kb_id": kb_id},
                status_code=404,
            )

        conversation = self._conversation_service.ensure_conversation(
            kb_id=kb_id,
            conversation_id=conversation_id,
            title=question.strip()[:50] if question.strip() else None,
        )

        topk = topk or kb.config.get("topk", self._settings.rag_topk)
        threshold = threshold if threshold is not None else kb.config.get(
            "threshold", self._settings.rag_threshold
        )
        rerank_enabled = (
            rerank_enabled
            if rerank_enabled is not None
            else kb.config.get("rerank_enabled", self._settings.rerank_enabled)
        )
        min_chunks = self._settings.rag_min_evidence_chunks

        total_start = time.perf_counter()
        query_vector = self._embedder.embed_query(question)
        retrieve_start = time.perf_counter()
        hits = self._vector_store.search(
            kb_id=kb_id,
            query_vector=query_vector,
            topk=topk,
            filters=filters,
        )
        retrieve_ms = int((time.perf_counter() - retrieve_start) * 1000)
        refusal_reason = self._get_refusal_reason(question, hits, threshold, min_chunks)
        if refusal_reason is not None:
            total_ms = int((time.perf_counter() - total_start) * 1000)
            response = self._build_refusal(
                question,
                request_id,
                conversation.conversation_id,
                refusal_reason,
                retrieve_ms,
                0,
                total_ms,
            )
            self._save_messages(conversation.conversation_id, question, response)
            self._log_ask(
                request_id=request_id,
                kb_id=kb_id,
                topk=topk,
                threshold=threshold,
                rerank_enabled=rerank_enabled,
                retrieve_ms=retrieve_ms,
                rerank_ms=0,
                context_ms=0,
                generate_ms=0,
                total_ms=total_ms,
                hits=hits,
                refusal_reason=refusal_reason,
            )
            return response

        rerank_ms = 0
        if rerank_enabled:
            rerank_start = time.perf_counter()
            hits = self._reranker.rerank(question, hits)
            rerank_ms = int((time.perf_counter() - rerank_start) * 1000)

        context_start = time.perf_counter()
        context_result = self._context_builder.build(hits)
        context_ms = int((time.perf_counter() - context_start) * 1000)
        if not context_result.hits:
            total_ms = int((time.perf_counter() - total_start) * 1000)
            response = self._build_refusal(
                question,
                request_id,
                conversation.conversation_id,
                "LOW_COVERAGE",
                retrieve_ms,
                0,
                total_ms,
            )
            self._save_messages(conversation.conversation_id, question, response)
            self._log_ask(
                request_id=request_id,
                kb_id=kb_id,
                topk=topk,
                threshold=threshold,
                rerank_enabled=rerank_enabled,
                retrieve_ms=retrieve_ms,
                rerank_ms=rerank_ms,
                context_ms=context_ms,
                generate_ms=0,
                total_ms=total_ms,
                hits=context_result.hits,
                refusal_reason="LOW_COVERAGE",
            )
            return response

        citations = self._build_citations(context_result.hits, debug)
        generate_start = time.perf_counter()
        if self._settings.vllm_enabled:
            answer = self._llm_client.generate(question=question, context=context_result.context)
        else:
            answer = self._build_answer(citations)
        generate_ms = int((time.perf_counter() - generate_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        response = AskResult(
            answer=answer,
            refusal=False,
            refusal_reason=None,
            suggestions=[],
            citations=citations,
            conversation_id=conversation.conversation_id,
            message_id=new_id("msg"),
            timing={
                "retrieve_ms": retrieve_ms,
                "rerank_ms": rerank_ms,
                "context_ms": context_ms,
                "generate_ms": generate_ms,
                "total_ms": total_ms,
            },
            request_id=request_id,
        )
        self._save_messages(conversation.conversation_id, question, response)
        self._log_ask(
            request_id=request_id,
            kb_id=kb_id,
            topk=topk,
            threshold=threshold,
            rerank_enabled=rerank_enabled,
            retrieve_ms=retrieve_ms,
            rerank_ms=rerank_ms,
            context_ms=context_ms,
            generate_ms=generate_ms,
            total_ms=total_ms,
            hits=context_result.hits,
            refusal_reason=None,
        )
        return response

    def _get_refusal_reason(
        self,
        question: str,
        hits: list[VectorHit],
        threshold: float,
        min_chunks: int,
    ) -> str | None:
        """判断是否需要拒答并返回原因码。"""

        if not hits:
            return "NO_EVIDENCE"
        if hits[0].score < threshold:
            return "LOW_SCORE"
        if len(hits) < min_chunks:
            return "LOW_EVIDENCE"
        if not self._has_keyword_overlap(question, hits):
            return "LOW_COVERAGE"
        return None

    def _build_refusal(
        self,
        question: str,
        request_id: str | None,
        conversation_id: str | None,
        refusal_reason: str,
        retrieve_ms: int,
        generate_ms: int,
        total_ms: int,
    ) -> AskResult:
        """构建拒答响应。"""

        return AskResult(
            answer="当前知识库中未找到足够证据，无法给出可靠答案。",
            refusal=True,
            refusal_reason=refusal_reason,
            suggestions=[
                "建议到教务处官网查询相关规定",
                f"建议关键词：{question} 条件",
            ],
            citations=[],
            conversation_id=conversation_id,
            message_id=new_id("msg"),
            timing={
                "retrieve_ms": retrieve_ms,
                "rerank_ms": 0,
                "context_ms": 0,
                "generate_ms": generate_ms,
                "total_ms": total_ms,
            },
            request_id=request_id,
        )

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
        return text.strip().replace("\n", " ")[:limit]

    def _build_answer(self, citations: list[CitationDTO]) -> str:
        """构建答案文本。"""

        if not citations:
            return "未找到可用证据。"
        head = citations[0].snippet
        return f"根据检索到的证据，相关内容如下：[1] {head}"

    def _has_keyword_overlap(self, question: str, hits: list[VectorHit]) -> bool:
        """判断问题与命中文本是否存在关键词覆盖。"""

        tokens = self._tokenize_question(question)
        if not tokens:
            return True
        for hit in hits:
            text = (hit.payload.get("text") or "").lower()
            if any(token in text for token in tokens):
                return True
        return False

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

    def _save_messages(
        self, conversation_id: str, question: str, response: AskResult
    ) -> None:
        """保存问答消息。"""

        self._conversation_service.save_message(
            conversation_id=conversation_id,
            role="user",
            content=question,
            refusal=False,
            refusal_reason=None,
            timing=None,
            citations=None,
        )
        citations = [item.model_dump() for item in response.citations]
        self._conversation_service.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.answer,
            refusal=response.refusal,
            refusal_reason=response.refusal_reason,
            timing=response.timing,
            citations=citations,
            message_id=response.message_id,
        )
