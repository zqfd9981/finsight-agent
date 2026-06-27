from enum import Enum


class SupportStrength(str, Enum):
    """共享契约中定义的证据支撑强度枚举。"""

    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"
