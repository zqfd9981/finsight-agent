from __future__ import annotations

import streamlit as st

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.components.response_summary_card import (
    build_response_summary_card_data,
)
from frontend.streamlit_app.state.workbench_state import (
    get_last_analysis_result,
    set_last_analysis_result,
)
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_analysis_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    intent = ""
    strategy = ""
    evidence_ref_count = 0
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            intent = str(block.payload_summary.get("intent") or "")
        if block.block_type == "execution":
            observations = block.payload_summary.get("stage_observations", [])
            for item in observations:
                stage_name = item.get("stage_name", "")
                key_outputs = item.get("key_outputs", {})
                if stage_name == "collect_event_context":
                    strategy = str(key_outputs.get("strategy") or "")
                if stage_name == "retrieve_evidence":
                    evidence_ref_count = int(
                        key_outputs.get("evidence_ref_count") or 0
                    )
    return {
        "summary": getattr(envelope.response, "summary", ""),
        "response_type": envelope.response.response_type,
        "intent": intent,
        "strategy": strategy,
        "degraded": envelope.response.response_type != "success",
        "evidence_ref_count": evidence_ref_count,
        "session_id": envelope.session_id,
    }


def render_analysis_view(client: WorkbenchApiClient) -> None:
    """分析视图渲染壳：表单 → 调后端 → 渲染最近 envelope。"""

    st.subheader("分析视图")
    with st.form("analysis_run_form", clear_on_submit=False):
        query = st.text_area("用户问题", value="", key="analysis_query")
        session_id = st.text_input(
            "会话标识（追问时填写）", value="", key="analysis_session_id"
        )
        include_trace = st.checkbox(
            "请求 trace", value=True, key="analysis_include_trace"
        )
        submitted = st.form_submit_button("运行分析")

    if submitted and query.strip():
        try:
            envelope = client.send_request(
                query=query.strip(),
                session_id=session_id.strip() or None,
                include_trace=include_trace,
            )
            set_last_analysis_result(st.session_state, envelope)
            st.session_state["_last_analysis_error"] = None
        except Exception as exc:  # noqa: BLE001
            st.session_state["_last_analysis_error"] = str(exc)
            st.error(f"后端请求失败：{exc}")

    error_msg = st.session_state.get("_last_analysis_error")
    if error_msg:
        st.warning(f"上一次请求未成功：{error_msg}")

    envelope = get_last_analysis_result(st.session_state)
    if envelope is not None:
        view = build_analysis_view_model(envelope)
        card = build_response_summary_card_data(envelope)
        st.markdown(f"**会话标识：** `{card['session_id']}`")
        st.markdown(f"**响应类型：** `{card['response_type']}`")
        st.markdown(f"**摘要：** {view['summary']}")
        st.markdown(
            f"**意图：** `{view['intent']}`　"
            f"**策略：** `{view['strategy']}`　"
            f"**证据引用数：** {view['evidence_ref_count']}"
        )
        if view["degraded"]:
            st.warning("当前结果为降级结果，请谨慎使用。")
