from enum import Enum


class StageName(str, Enum):
    """Shared top-level stage names."""

    COLLECT_EVENT_CONTEXT = "collect_event_context"
    ANALYZE_TARGETS = "analyze_targets"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    SYNTHESIZE_REPORT = "synthesize_report"
    SYNTHESIZE_EVENT_ANSWER = "synthesize_event_answer"
    QUERY_STRUCTURED_DATA = "query_structured_data"
    SYNTHESIZE_BRIEF_ANSWER = "synthesize_brief_answer"
