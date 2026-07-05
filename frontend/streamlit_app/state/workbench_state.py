from __future__ import annotations

from collections.abc import MutableMapping

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


LAST_ANALYSIS_RESULT_KEY = "last_analysis_result"
SELECTED_EVAL_CASE_ID_KEY = "selected_eval_case_id"


def get_last_analysis_result(
    bucket: MutableMapping[str, object],
) -> AnalysisResponseEnvelope | None:
    payload = bucket.get(LAST_ANALYSIS_RESULT_KEY)
    return payload if isinstance(payload, AnalysisResponseEnvelope) else None


def set_last_analysis_result(
    bucket: MutableMapping[str, object],
    envelope: AnalysisResponseEnvelope,
) -> None:
    bucket[LAST_ANALYSIS_RESULT_KEY] = envelope


def get_selected_eval_case_id(bucket: MutableMapping[str, object]) -> str | None:
    payload = bucket.get(SELECTED_EVAL_CASE_ID_KEY)
    return payload if isinstance(payload, str) and payload else None


def set_selected_eval_case_id(
    bucket: MutableMapping[str, object],
    case_id: str | None,
) -> None:
    if case_id:
        bucket[SELECTED_EVAL_CASE_ID_KEY] = case_id
    else:
        bucket.pop(SELECTED_EVAL_CASE_ID_KEY, None)
