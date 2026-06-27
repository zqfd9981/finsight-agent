from enum import Enum


class StageName(str, Enum):
    """共享契约中定义的 V1 顶层阶段枚举。"""

    COLLECT_EVENT_CONTEXT = "collect_event_context"
    ANALYZE_TARGETS = "analyze_targets"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    SYNTHESIZE_REPORT = "synthesize_report"
    QUERY_STRUCTURED_DATA = "query_structured_data"
    SYNTHESIZE_BRIEF_ANSWER = "synthesize_brief_answer"
