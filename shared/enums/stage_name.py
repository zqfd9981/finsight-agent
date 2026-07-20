from enum import Enum


class StageName(str, Enum):
    """Shared top-level stage names."""

    COLLECT_EVENT_CONTEXT = "collect_event_context"
    ANALYZE_TARGETS = "analyze_targets"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    QUERY_STRUCTURED_DATA = "query_structured_data"
    REFLECT_AND_REQUERY = "reflect_and_requery"
    SYNTHESIZE_ANSWER = "synthesize_answer"
    VERIFY_ANSWER = "verify_answer"
