from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

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


PSEUDO_STREAM_STEPS = (
    ("routing", "Routing", "识别问题意图与上下文"),
    ("planning", "Planning", "规划执行链路"),
    ("execution", "Execution", "等待分析阶段完成"),
    ("response", "Response", "整理最终回答"),
)


def _normalize_response_payload(
    envelope: AnalysisResponseEnvelope,
) -> dict[str, object]:
    response = envelope.response
    response_type = str(getattr(response, "response_type", "") or "").strip()
    summary = str(getattr(response, "summary", "") or "").strip()
    if not summary:
        summary = str(getattr(response, "partial_answer", "") or "").strip()
    return {
        "response_type": response_type,
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


def build_pseudo_stream_timeline(elapsed_seconds: float) -> list[dict[str, str]]:
    active_index = min(int(elapsed_seconds // 1.2), len(PSEUDO_STREAM_STEPS) - 1)
    timeline: list[dict[str, str]] = []
    for idx, (step_key, title, detail) in enumerate(PSEUDO_STREAM_STEPS):
        if idx < active_index:
            status = "completed"
        elif idx == active_index:
            status = "running"
        else:
            status = "pending"
        timeline.append(
            {
                "step_key": step_key,
                "title": title,
                "detail": detail,
                "status": status,
            }
        )
    return timeline


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
    response_payload = _normalize_response_payload(envelope)
    return {
        **response_payload,
        "intent": intent,
        "strategy": strategy,
        "degraded": response_payload["response_type"] != "success",
        "evidence_ref_count": evidence_ref_count,
        "session_id": envelope.session_id,
    }


def _render_pseudo_stream(progress_placeholder: st.delta_generator.DeltaGenerator, elapsed_seconds: float) -> None:
    timeline = build_pseudo_stream_timeline(elapsed_seconds)
    icon_map = {
        "completed": "ok",
        "running": "run",
        "pending": "wait",
    }
    with progress_placeholder.container():
        st.markdown("**实时执行链路**")
        st.caption(f"请求处理中，已等待 {elapsed_seconds:.1f}s")
        for item in timeline:
            icon = icon_map[item["status"]]
            st.write(
                f"- `{item['title']}` [{icon}] {item['detail']}"
            )


def _run_request_with_pseudo_stream(
    client: WorkbenchApiClient,
    *,
    query: str,
    session_id: str | None,
    include_trace: bool,
) -> AnalysisResponseEnvelope:
    progress_placeholder = st.empty()
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.send_request,
            query=query,
            session_id=session_id,
            include_trace=include_trace,
        )
        try:
            while not future.done():
                _render_pseudo_stream(progress_placeholder, time.monotonic() - start)
                time.sleep(0.35)
            return future.result()
        finally:
            progress_placeholder.empty()


def _render_report_blocks(report_blocks: list[dict[str, object]]) -> None:
    if not report_blocks:
        return
    st.markdown("**详细结果**")
    for block in report_blocks:
        title = str(block.get("title") or block.get("block_type") or "结果块")
        with st.expander(title, expanded=True):
            items = list(block.get("items") or [])
            if not items:
                st.caption("暂无明细项。")
                continue
            for item in items:
                company_name = str(item.get("company_name") or "").strip()
                doc_type = str(item.get("doc_type") or "").strip()
                excerpt = str(item.get("excerpt") or "").strip()
                prefix = " / ".join(
                    piece for piece in (company_name, doc_type) if piece
                )
                if prefix:
                    st.markdown(f"- **{prefix}**：{excerpt}")
                else:
                    st.markdown(f"- {excerpt}")


def _render_response_details(view: dict[str, object]) -> None:
    answer_markdown = str(view.get("answer_markdown") or "").strip()
    if answer_markdown:
        st.markdown(answer_markdown)
    else:
        st.markdown(f"**最终回答：** {view['summary']}")
    _render_report_blocks(list(view.get("report_blocks") or []))

    uncertainty_notes = list(view.get("uncertainty_notes") or [])
    if uncertainty_notes:
        st.markdown("**不确定性提示**")
        for note in uncertainty_notes:
            st.write(f"- {note}")

    next_actions = list(view.get("next_actions") or [])
    if next_actions:
        st.markdown("**建议下一步**")
        for action in next_actions:
            st.write(f"- {action}")

    if view.get("notes"):
        st.caption(str(view["notes"]))


def render_analysis_view(client: WorkbenchApiClient) -> None:
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
            envelope = _run_request_with_pseudo_stream(
                client,
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
        st.markdown(
            f"**意图：** `{view['intent']}`　"
            f"**策略：** `{view['strategy']}`　"
            f"**证据引用数：** {view['evidence_ref_count']}"
        )
        _render_response_details(view)
        if view["degraded"]:
            st.warning("当前结果为降级结果，请结合调试视图判断可信度。")
