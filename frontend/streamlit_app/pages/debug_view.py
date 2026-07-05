from __future__ import annotations

import streamlit as st

from frontend.streamlit_app.state.workbench_state import get_last_analysis_result
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_debug_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    routing: dict[str, object] = {}
    planning: dict[str, object] = {}
    execution: dict[str, object] = {"stage_statuses": {}, "stage_observations": []}
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            routing = dict(block.payload_summary)
        elif block.block_type == "planning":
            planning = dict(block.payload_summary)
        elif block.block_type == "execution":
            execution = dict(block.payload_summary)
    stages = list(execution.get("stage_observations", []))
    return {
        "routing": routing,
        "planning": planning,
        "execution": execution,
        "stages": stages,
        "response_type": envelope.response.response_type,
    }


def render_debug_view() -> None:
    """调试视图渲染壳：分开展示 Routing / Planning / Execution + 阶段列表。"""

    st.subheader("调试视图")
    envelope = get_last_analysis_result(st.session_state)
    if envelope is None:
        st.info("请先在「分析视图」运行一次分析。")
        return

    model = build_debug_view_model(envelope)
    with st.expander("Routing", expanded=True):
        st.json(model["routing"])
    with st.expander("Planning", expanded=False):
        st.json(model["planning"])
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
