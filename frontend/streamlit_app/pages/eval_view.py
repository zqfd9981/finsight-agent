from __future__ import annotations

import streamlit as st

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.state.models import (
    EventEvalCaseView,
    EventReplayRecordView,
    EventReplayRunView,
)


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


def render_eval_view(client: WorkbenchApiClient) -> None:
    """评测视图渲染壳：拉样本 → 多选 → replay → 渲染 summary + records。"""

    cases_key = "_eval_cases"
    run_key = "_eval_run"

    st.subheader("评测视图")
    if st.button("刷新样本列表"):
        try:
            st.session_state[cases_key] = client.fetch_event_cases()
            st.session_state[run_key] = None
        except Exception as exc:  # noqa: BLE001
            st.error(f"获取样本失败：{exc}")

    cases: list[EventEvalCaseView] = st.session_state.get(cases_key, [])
    case_ids = [case.case_id for case in cases]
    selected = st.multiselect("选择 case_id（可多选）", case_ids)

    if st.button("运行 replay"):
        if not selected:
            st.warning("请先选择至少一个 case_id")
        else:
            try:
                st.session_state[run_key] = client.fetch_event_replay(case_ids=selected)
            except Exception as exc:  # noqa: BLE001
                st.error(f"replay 失败：{exc}")

    run: EventReplayRunView | None = st.session_state.get(run_key)
    if run is not None:
        model = build_eval_view_model(run, cases=cases)
        st.json(model["summary"])
        records = model.get("records") or []
        if records:
            st.dataframe(records)
        else:
            st.caption("（无可显示的 records）")
        if model.get("selected_detail"):
            st.markdown("**选中 case 详情：**")
            st.json(model["selected_detail"])
