from enum import Enum


class ResponseMode(str, Enum):
    """最终响应模式枚举，由 orchestrator 查表决定，driving synthesize_answer stage 切换 prompt 模板。"""

    REPORT = "report"
    BRIEF_ANSWER = "brief_answer"
    EVENT_ANSWER = "event_answer"
    DIRECT = "direct"
