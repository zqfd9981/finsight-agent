from enum import Enum


class Intent(str, Enum):
    """共享契约中定义的 V1 intent 枚举。"""

    METRIC_LOOKUP = "metric_lookup"
    EVENT_IMPACT_ANALYSIS = "event_impact_analysis"
    EVIDENCE_LOOKUP = "evidence_lookup"
    OUT_OF_SCOPE = "out_of_scope"
