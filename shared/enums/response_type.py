from enum import Enum


class ResponseType(str, Enum):
    """共享契约中定义的响应类型枚举。"""

    SUCCESS = "success"
    DEGRADED = "degraded"
    GUARDRAIL = "guardrail"
    ERROR = "error"
