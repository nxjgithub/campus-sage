from __future__ import annotations

from app.rag.reranker import SimpleReranker
from app.rag.vector_store import VectorHit


def test_rerank_prefers_exact_content_match_over_higher_vector_score() -> None:
    reranker = SimpleReranker()
    hits = [
        VectorHit(
            score=0.95,
            payload={
                "doc_name": "学生手册.pdf",
                "section_path": "奖助管理",
                "text": "奖学金评定办法与综合测评说明。",
            },
        ),
        VectorHit(
            score=0.72,
            payload={
                "doc_name": "本科生学籍管理规定.pdf",
                "section_path": "转专业",
                "text": "转专业申请条件包括成绩排名要求、无违纪记录和学院审核。",
            },
        ),
    ]

    ranked = reranker.rerank("转专业申请条件", hits)

    assert ranked[0].payload["doc_name"] == "本科生学籍管理规定.pdf"


def test_rerank_prefers_title_and_section_match() -> None:
    reranker = SimpleReranker()
    hits = [
        VectorHit(
            score=0.88,
            payload={
                "doc_name": "教务通知汇编.pdf",
                "section_path": "常见问题",
                "text": "学生成绩查询、补考报名和选课操作说明。",
            },
        ),
        VectorHit(
            score=0.61,
            payload={
                "doc_name": "本科生转专业实施细则.pdf",
                "section_path": "成绩要求",
                "text": "申请人须满足学院公布的基础条件。",
            },
        ),
    ]

    ranked = reranker.rerank("转专业成绩要求", hits)

    assert ranked[0].payload["doc_name"] == "本科生转专业实施细则.pdf"


def test_rerank_returns_original_hits_for_blank_question() -> None:
    reranker = SimpleReranker()
    hits = [
        VectorHit(
            score=0.5,
            payload={
                "doc_name": "demo.pdf",
                "section_path": None,
                "text": "测试文本",
            },
        )
    ]

    ranked = reranker.rerank("   ", hits)

    assert ranked is hits
