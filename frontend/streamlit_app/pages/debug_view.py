from __future__ import annotations

import streamlit as st

from frontend.streamlit_app.state.workbench_state import get_last_analysis_result
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def _normalize_response_payload(
    envelope: AnalysisResponseEnvelope,
) -> dict[str, object]:
    response = envelope.response
    summary = str(getattr(response, "summary", "") or "").strip()
    if not summary:
        summary = str(getattr(response, "partial_answer", "") or "").strip()
    return {
        "response_type": str(getattr(response, "response_type", "") or "").strip(),
        "summary": summary,
        "answer_markdown": str(getattr(response, "answer_markdown", "") or "").strip(),
        "report_blocks": list(getattr(response, "report_blocks", []) or []),
        "uncertainty_notes": list(getattr(response, "uncertainty_notes", []) or []),
        "next_actions": list(
            getattr(response, "next_actions", None)
            or getattr(response, "suggested_next_actions", [])
            or []
        ),
        "reason_code": str(getattr(response, "reason_code", "") or "").strip(),
        "progress_state": str(getattr(response, "progress_state", "") or "").strip(),
        "trace_refs": list(getattr(response, "trace_refs", []) or []),
        "notes": getattr(response, "notes", None),
    }


def build_debug_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    routing: dict[str, object] = {}
    stage_planning: dict[str, object] = {}
    execution: dict[str, object] = {"stage_statuses": {}, "stage_observations": []}
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            routing = dict(block.payload_summary)
        elif block.block_type == "stage_planning":
            stage_planning = dict(block.payload_summary)
        elif block.block_type == "execution":
            execution = dict(block.payload_summary)
    stages = list(execution.get("stage_observations", []))
    return {
        "routing": routing,
        "stage_planning": stage_planning,
        "execution": execution,
        "stages": stages,
        "response_type": str(getattr(envelope.response, "response_type", "") or ""),
        "final_response": _normalize_response_payload(envelope),
    }


def render_debug_view() -> None:
    st.subheader("调试视图")
    envelope = get_last_analysis_result(st.session_state)
    if envelope is None:
        st.info("请先在“分析视图”运行一次分析。")
        return

    model = build_debug_view_model(envelope)
    with st.expander("Final Response", expanded=True):
        st.json(model["final_response"])
    with st.expander("Routing", expanded=True):
        st.json(model["routing"])
    with st.expander("Stage Planning", expanded=False):
        st.json(model["stage_planning"])
    with st.expander("Execution", expanded=True):
        st.json(model["execution"])
    st.markdown("**Stage 观察：**")
    stages = model.get("stages") or []
    if not stages:
        st.caption("（暂无 stage 观察）")
    for stage in stages:
        stage_name = stage.get("stage_name", "<unknown>")
        status = stage.get("status", "degraded")
        st.write(f"- `{stage_name}` ({status})")
