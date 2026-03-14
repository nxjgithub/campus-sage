from __future__ import annotations

from scripts.export_eval_inventory import (
    DocumentInventory,
    build_collection_name,
    build_inventory_payload,
    summarize_documents,
)


def test_summarize_documents_groups_points_by_doc() -> None:
    points = [
        {
            "doc_id": "doc_1",
            "doc_name": "本科生考试管理规定.pdf",
            "source_type": "pdf",
            "page_start": 8,
            "page_end": 8,
            "section_path": "补考",
        },
        {
            "doc_id": "doc_1",
            "doc_name": "本科生考试管理规定.pdf",
            "source_type": "pdf",
            "page_start": 5,
            "page_end": 6,
            "section_path": "缓考",
        },
        {
            "doc_id": "doc_1",
            "doc_name": "本科生考试管理规定.pdf",
            "source_type": "pdf",
            "page_start": 6,
            "page_end": 6,
            "section_path": "缓考",
        },
        {
            "doc_id": "doc_2",
            "doc_name": "本科生转专业实施细则.pdf",
            "source_type": "pdf",
            "page_start": 2,
            "page_end": 3,
            "section_path": "成绩要求",
        },
    ]

    documents = summarize_documents(points, section_sample_limit=3)

    assert documents == [
        DocumentInventory(
            doc_id="doc_1",
            doc_name="本科生考试管理规定.pdf",
            source_type="pdf",
            chunk_count=3,
            page_start_min=5,
            page_end_max=8,
            section_path_examples=["补考", "缓考"],
        ),
        DocumentInventory(
            doc_id="doc_2",
            doc_name="本科生转专业实施细则.pdf",
            source_type="pdf",
            chunk_count=1,
            page_start_min=2,
            page_end_max=3,
            section_path_examples=["成绩要求"],
        ),
    ]


def test_build_inventory_payload_serializes_documents() -> None:
    payload = build_inventory_payload(
        kb_id="kb_demo",
        collection_name="csage_kb_demo",
        documents=[
            DocumentInventory(
                doc_id="doc_1",
                doc_name="demo.pdf",
                source_type="pdf",
                chunk_count=2,
                page_start_min=1,
                page_end_max=2,
                section_path_examples=["第一章"],
            )
        ],
    )

    assert payload["kb_id"] == "kb_demo"
    assert payload["collection_name"] == "csage_kb_demo"
    assert payload["document_count"] == 1
    assert payload["documents"][0]["doc_name"] == "demo.pdf"


def test_build_collection_name_uses_prefix() -> None:
    assert build_collection_name("kb_123", "csage_") == "csage_kb_123"
