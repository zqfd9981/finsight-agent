"""工作台状态导出。"""

from .workbench_state import (
    get_last_analysis_result,
    get_selected_eval_case_id,
    set_last_analysis_result,
    set_selected_eval_case_id,
)

__all__ = [
    "get_last_analysis_result",
    "get_selected_eval_case_id",
    "set_last_analysis_result",
    "set_selected_eval_case_id",
]
