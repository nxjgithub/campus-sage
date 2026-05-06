from __future__ import annotations

import re

from app.rag.vector_store import VectorHit


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
        """对通知类常见意图词给额外权重，避免高向量分数压过章节命中。"""

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
        """统计问题中的领域短语被候选命中的数量，用作强排序特征。"""

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
        """判断短语是否缺乏区分度，避免进入重排特征。"""

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
