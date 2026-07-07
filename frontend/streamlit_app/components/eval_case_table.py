from __future__ import annotations

from frontend.streamlit_app.state.models import EventEvalCaseView, EventReplayRunView


def build_eval_case_table_rows(
    cases: list[EventEvalCaseView],
    replay_run: EventReplayRunView | None = None,
) -> list[dict[str, object]]:
    replay_status_by_case_id: dict[str, str] = {}
    replay_strategy_by_case_id: dict[str, str] = {}
    if replay_run is not None:
        for record in replay_run.records:
            statuses = [item["status"] for item in record.checks]
            derived_status = (
                "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
            )
            replay_status_by_case_id[record.case_id] = derived_status
            replay_strategy_by_case_id[record.case_id] = record.result.actual_strategy

    return [
        {
            "case_id": case.case_id,
            "query": case.query,
            "expected_strategy": case.expected_strategy,
            "allow_degraded": case.allow_degraded,
            "status": replay_status_by_case_id.get(case.case_id, "pending"),
            "actual_strategy": replay_strategy_by_case_id.get(case.case_id, ""),
        }
        for case in cases
    ]
