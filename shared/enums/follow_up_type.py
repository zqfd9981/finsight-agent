from enum import Enum


class FollowUpType(str, Enum):
    """路由阶段使用的追问关系枚举。"""

    NONE = "none"
    REDIRECT = "redirect"
    DRILLDOWN = "drilldown"
    COMPARE = "compare"
    EXPAND = "expand"
