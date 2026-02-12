"""评测模块入口（用于集中导出）。"""

from app.eval.dto import EvalItem, EvalResult, EvalSet
from app.eval.runner import run_eval

__all__ = ["EvalItem", "EvalSet", "EvalResult", "run_eval"]
