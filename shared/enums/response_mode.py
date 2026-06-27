from enum import Enum


class ResponseMode(str, Enum):
    """计划阶段使用的最终响应模式枚举。"""

    REPORT = "report"
    BRIEF_ANSWER = "brief_answer"
