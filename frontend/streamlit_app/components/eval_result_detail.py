from __future__ import annotations

from frontend.streamlit_app.state.models import EventEvalCaseView, EventReplayRecordView


def build_eval_result_detail_data(
    record: EventReplayRecordView,
    case: EventEvalCaseView | None = None,
) -> dict[str, object]:
    expected = None
    if case is not None:
        expected = {
            "expected_intent": case.expected_intent,
            "expected_strategy": case.expected_strategy,
            "allow_degraded": case.allow_degraded,
            "min_target_count": case.min_target_count,
            "expected_target_keywords": list(case.expected_target_keywords),
            "notes": case.notes,
        }

    return {
        "case_id": record.case_id,
        "query": record.query,
        "expected": expected,
        "actual": {
            "actual_intent": record.result.actual_intent,
            "actual_strategy": record.result.actual_strategy,
            "response_type": record.result.response_type,
            "degraded": record.result.degraded,
            "target_count": record.result.target_count,
            "evidence_ref_count": record.result.evidence_ref_count,
            "summary": record.result.summary,
            "failure_reason": record.result.failure_reason,
            "target_keywords": list(record.result.target_keywords),
        },
        "checks": list(record.checks),
    }
