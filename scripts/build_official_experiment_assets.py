from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.errors import AppError
from app.ingest.chunker import Chunker
from app.ingest.parser import DocumentParser


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}
GENERIC_WORDS = {
    "关于",
    "通知",
    "附件",
    "温馨提示",
    "四川轻化工大学",
    "学生",
    "学校",
    "工作",
    "活动",
    "办法",
    "指南",
    "公告",
}


def main() -> None:
    """基于正式文件目录生成论文 V11 使用的语料清单和评测集。"""

    parser = argparse.ArgumentParser(description="生成正式文件实验语料清单与评测集")
    parser.add_argument("--source-dir", default="data/正式文件", help="正式文件目录")
    parser.add_argument(
        "--eval-file",
        default="docs/examples/eval_set_official_formal_v11.json",
        help="输出评测集 JSON",
    )
    parser.add_argument(
        "--manifest-file",
        default="docs/examples/official_formal_corpus_v11_manifest.json",
        help="输出语料清单 JSON",
    )
    parser.add_argument("--chunk-size", type=int, default=500, help="统计分块大小")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="统计分块重叠")
    args = parser.parse_args()

    source_dir = ROOT_DIR / args.source_dir
    eval_file = ROOT_DIR / args.eval_file
    manifest_file = ROOT_DIR / args.manifest_file

    parser_service = DocumentParser()
    chunker = Chunker(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    documents: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []

    for path in sorted(source_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append({"doc_name": path.name, "reason": "文件类型暂不支持自动入库"})
            continue
        try:
            pages = parser_service.parse(path)
        except AppError as exc:
            skipped.append({"doc_name": path.name, "reason": exc.message})
            continue
        chunks = chunker.build(pages)
        title = normalize_title(path.stem)
        char_count = sum(len(page.text) for page in pages)
        documents.append(
            {
                "doc_name": path.name,
                "source_path": str(path.relative_to(ROOT_DIR)),
                "file_size_bytes": path.stat().st_size,
                "parsed_units": len(pages),
                "chunk_count": len(chunks),
                "char_count": char_count,
                "title": title,
            }
        )
        items.extend(build_questions(path.name, title))

    items.extend(out_of_scope_questions())
    eval_payload = {
        "name": "CampusSage正式文件扩展评测集V11",
        "description": "基于 data/正式文件 的真实校园通知、指南、附件和 PDF/DOCX 文档生成，包含知识库内检索问题与知识库外边界问题。",
        "source_dir": str(source_dir.relative_to(ROOT_DIR)),
        "document_count": len(documents),
        "skipped_count": len(skipped),
        "items": items,
    }
    manifest_payload = {
        "source_dir": str(source_dir.relative_to(ROOT_DIR)),
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "document_count": len(documents),
        "question_count": len(items),
        "in_scope_question_count": sum(1 for item in items if item["gold_doc_name"]),
        "out_of_scope_question_count": sum(1 for item in items if not item["gold_doc_name"]),
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "total_chunks": sum(item["chunk_count"] for item in documents),
        "total_chars": sum(item["char_count"] for item in documents),
        "documents": documents,
        "skipped": skipped,
    }

    eval_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    eval_file.write_text(json.dumps(eval_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_file.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "eval_file": str(eval_file.relative_to(ROOT_DIR)),
                "manifest_file": str(manifest_file.relative_to(ROOT_DIR)),
                "document_count": len(documents),
                "question_count": len(items),
                "skipped_count": len(skipped),
                "total_chunks": manifest_payload["total_chunks"],
                "total_chars": manifest_payload["total_chars"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def normalize_title(stem: str) -> str:
    """清理文件名中的副本标记与序号，得到适合出题的标题。"""

    title = re.sub(r"^\d+_", "", stem).strip()
    title = re.sub(r"\(\d+\)$", "", title).strip()
    title = re.sub(r"（\d+）$", "", title).strip()
    return title


def build_questions(doc_name: str, title: str) -> list[dict[str, Any]]:
    """为单个正式文件构造概述题和主题题。"""

    topic = topic_question(title)
    return [
        {
            "question": f"请概述《{title}》的核心内容。",
            "expected": title,
            "gold_doc_name": doc_name,
            "gold_doc_id": None,
            "gold_page_start": None,
            "gold_page_end": None,
            "question_type": "summary",
            "source": "official_file",
        },
        {
            "question": f"根据《{title}》，{topic}",
            "expected": title,
            "gold_doc_name": doc_name,
            "gold_doc_id": None,
            "gold_page_start": None,
            "gold_page_end": None,
            "question_type": "topic_detail",
            "source": "official_file",
        },
    ]


def topic_question(title: str) -> str:
    """根据标题中的业务关键词生成更接近真实咨询场景的问题。"""

    if has_any(title, "重补修", "补考"):
        return "重补修手续办理和补考确认有哪些时间或流程要求？"
    if has_any(title, "留校", "暑假"):
        return "暑假留校或假期学生管理需要注意哪些申请、安全和管理要求？"
    if has_any(title, "交通", "非机动车", "通行证", "驾驶", "骑行"):
        return "校园交通安全、非机动车通行或通行证办理有哪些要求？"
    if has_any(title, "自助打印", "证明材料"):
        return "自助打印终端或证明材料办理支持哪些事项和操作方式？"
    if has_any(title, "就业", "求职", "创业", "生源", "离校", "补采集"):
        return "毕业生就业、求职创业补贴或离校信息填写有哪些办理要求？"
    if has_any(title, "征兵", "义务兵", "军士", "入伍"):
        return "学生应征入伍、义务兵或直招军士相关工作有哪些安排？"
    if has_any(title, "安全", "防火", "诈骗", "保密", "网络安全", "地震", "国防"):
        return "校园安全教育、风险防范或应急技能学习有哪些重点要求？"
    if has_any(title, "心理"):
        return "心理咨询服务或心理知识比赛有哪些安排和参与要求？"
    if has_any(title, "宪法", "传统文化", "社区", "寝室", "关工委", "文明"):
        return "校园文化、学生社区或文明寝室建设相关活动有哪些安排？"
    if has_any(title, "系统", "平台", "使用手册", "操作指南", "轻风化雨"):
        return "相关系统平台的登录、信息维护或操作步骤有哪些注意事项？"
    if has_any(title, "公交", "年票", "火车优惠卡", "学生证"):
        return "学生证、公交卡、年票或火车优惠卡相关事项如何办理？"
    keywords = "、".join(select_keywords(title)[:4]) or title
    return f"关于{keywords}，该文件说明了哪些办理事项和注意要求？"


def has_any(text: str, *keywords: str) -> bool:
    """判断标题是否包含任一业务关键词。"""

    return any(keyword in text for keyword in keywords)


def select_keywords(title: str) -> list[str]:
    """从标题中抽取少量可读关键词。"""

    tokens = re.split(r"[\s，。、《》“”\"（）()【】_\-—]+", title)
    return [
        token
        for token in tokens
        if token and token not in GENERIC_WORDS and len(token) >= 2
    ]


def out_of_scope_questions() -> list[dict[str, Any]]:
    """构造知识库外问题，验证证据不足时拒答。"""

    questions = [
        "今天学校第一食堂午餐每个窗口具体卖什么菜？",
        "明天从成都飞北京的最低机票价格是多少？",
        "请查询我个人本学期每门课程的具体成绩。",
        "学校附近哪家火锅店今晚不用排队？",
        "请帮我预约明天上午十点的医院口腔科号源。",
        "今年世界杯决赛比分是多少？",
        "请给出我校园卡当前余额和最近三笔消费记录。",
        "请预测下个月比特币价格会涨到多少。",
        "请告诉我某位同学的身份证号码和联系电话。",
        "请生成一份无需证明即可领取补贴的内部审批名单。",
    ]
    return [
        {
            "question": question,
            "expected": "知识库中没有足够证据，应拒答并建议补充数据或查询官方渠道。",
            "gold_doc_name": None,
            "gold_doc_id": None,
            "gold_page_start": None,
            "gold_page_end": None,
            "question_type": "out_of_scope",
            "source": "boundary_case",
        }
        for question in questions
    ]


if __name__ == "__main__":
    main()
