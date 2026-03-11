"""拒答下一步建议动作定义。"""

from __future__ import annotations

from typing import Literal, get_args

NextStepAction = Literal[
    "search_keyword",
    "rewrite_question",
    "add_context",
    "check_official_source",
    "verify_kb_scope",
]
"""拒答下一步建议动作枚举。"""

NEXT_STEP_ACTIONS = tuple(get_args(NextStepAction))
"""所有允许的拒答动作列表。"""
