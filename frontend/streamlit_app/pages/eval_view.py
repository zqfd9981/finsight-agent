from __future__ import annotations

from frontend.streamlit_app.state.models import EventEvalCaseView, EventReplayRecordView, EventReplayRunView


def build_eval_view_model(
    replay_run: EventReplayRunView,
    *,
    cases: list[EventEvalCaseView] | None = None,
    status_filter: str = "all",
    selected_case_id: str | None = None,
) -> dict[str, object]:
    case_by_id = {case.case_id: case for case in (cases or [])}
    filtered_records: list[dict[str, object]] = []
    selected_record: EventReplayRecordView | None = None

    for record in replay_run.records:
        statuses = [item["status"] for item in record.checks]
        derived_status = (
            "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
        )
        if status_filter != "all" and derived_status != status_filter:
            continue

        filtered_records.append(
            {
                "case_id": record.case_id,
                "query": record.query,
                "status": derived_status,
                "expected_strategy": case_by_id.get(record.case_id).expected_strategy
                if record.case_id in case_by_id
                else "",
                "actual_strategy": record.result.actual_strategy,
                "degraded": record.result.degraded,
                "target_count": record.result.target_count,
            }
        )
        if selected_case_id and record.case_id == selected_case_id:
            selected_record = record

    if selected_record is None and replay_run.records:
        selected_record = next(
            (
                record
                for record in replay_run.records
                if any(item["case_id"] == record.case_id for item in filtered_records)
            ),
            None,
        )

    selected_detail = None
    if selected_record is not None:
        selected_detail = {
            "case_id": selected_record.case_id,
            "query": selected_record.query,
            "expected": case_by_id.get(selected_record.case_id),
            "result": selected_record.result,
            "checks": list(selected_record.checks),
        }

    return {
        "summary": {
            "total": replay_run.summary.total,
            "pass": replay_run.summary.pass_count,
            "warn": replay_run.summary.warn_count,
            "fail": replay_run.summary.fail_count,
        },
        "records": filtered_records,
        "selected_detail": selected_detail,
    }
