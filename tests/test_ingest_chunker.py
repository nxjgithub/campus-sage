from __future__ import annotations

from app.ingest.chunker import Chunker
from app.ingest.parser import ParsedPage


def test_chunker_builds_notice_section_paths() -> None:
    """通知类 PDF 文本应按标题和编号小节建立可检索的章节路径。"""

    page = ParsedPage(
        page_number=1,
        text=(
            "关于四川轻化工大学专属版玻尔AI科研平台首门AI科研素养基础课学习的通知\n"
            "各学院、各位同学：请按要求完成课程学习。\n"
            "一、课程内容\n"
            "课程围绕 AI 科研素养、平台使用和论文检索展开。\n"
            "二、学习要求\n"
            "学生须在规定时间内完成学习，并按平台要求提交记录。"
        ),
    )

    chunks = Chunker(chunk_size=120, chunk_overlap=20).build([page])

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks[0].section_path == "关于四川轻化工大学专属版玻尔AI科研平台首门AI科研素养基础课学习的通知"
    assert (
        chunks[1].section_path
        == "关于四川轻化工大学专属版玻尔AI科研平台首门AI科研素养基础课学习的通知/一、课程内容"
    )
    assert (
        chunks[2].section_path
        == "关于四川轻化工大学专属版玻尔AI科研平台首门AI科研素养基础课学习的通知/二、学习要求"
    )
    assert "课程围绕 AI 科研素养" in chunks[1].text
    assert "规定时间内完成学习" in chunks[2].text


def test_chunker_splits_long_notice_on_sentence_boundary() -> None:
    """长小节应优先在完整句子边界切分，并保留小节标题作为语义锚点。"""

    page = ParsedPage(
        page_number=2,
        text=(
            "一、学习安排\n"
            "第一阶段登录玻尔AI科研平台完成账号绑定。"
            "第二阶段学习AI科研素养基础课并完成章节测验。"
            "第三阶段查看学习记录并确认个人信息。"
            "第四阶段如遇平台问题及时联系学院管理员。"
        ),
    )

    chunks = Chunker(chunk_size=58, chunk_overlap=12).build([page])

    assert len(chunks) >= 3
    assert all(chunk.section_path == "一、学习安排" for chunk in chunks)
    assert all(chunk.text.startswith("一、学习安排") for chunk in chunks)
    assert chunks[0].text.endswith("。")
    assert "第二阶段学习AI科研素养基础课" in "\n".join(chunk.text for chunk in chunks)


def test_chunker_preserves_page_section_path_for_structured_documents() -> None:
    """已有结构化 section_path 时应作为父路径保留，页内小节继续追加。"""

    page = ParsedPage(
        page_number=None,
        section_path="培养方案",
        text="一、适用对象\n本科生适用。\n二、课程要求\n需完成必修课程。",
    )

    chunks = Chunker(chunk_size=80, chunk_overlap=10).build([page])

    assert chunks[0].section_path == "培养方案/一、适用对象"
    assert chunks[1].section_path == "培养方案/二、课程要求"


def test_chunker_splits_oversized_table_line() -> None:
    """超长表格行也应退回窗口切分，避免单个 chunk 明显超预算。"""

    table_line = "列1 | 列2 | " + "很长内容" * 80
    page = ParsedPage(page_number=1, text=table_line)

    chunks = Chunker(chunk_size=80, chunk_overlap=10).build([page])

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 80 for chunk in chunks)
    assert chunks[0].text.startswith("列1 | 列2 |")


def test_chunker_preserves_english_phrase_spaces() -> None:
    """英文短语中的正常空格不能被清洗逻辑粘连。"""

    page = ParsedPage(
        page_number=1,
        text="课程内容\nAI academic search\nand knowledge base 能力介绍。",
    )

    chunks = Chunker(chunk_size=120, chunk_overlap=10).build([page])
    content = "\n".join(chunk.text for chunk in chunks)

    assert "AI academic search and knowledge base" in content
    assert "AIacademicsearch" not in content
