from __future__ import annotations

from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Thread
import time
from typing import Any

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
from shared.contracts.analysis_stream_event import AnalysisStreamEvent


STAGE_LABELS = {
    "routing": "Routing",
    "stage_planning": "Stage Planning",
    "collect_event_context": "Collect event context",
    "analyze_targets": "Analyze targets",
    "rerank": "Rerank",
    "retrieve_evidence": "Retrieve evidence",
    "query_structured_data": "Query structured data",
    "synthesize_brief_answer": "Synthesize brief answer",
    "synthesize_event_answer": "Synthesize event answer",
    "synthesize_report": "Synthesize report",
}


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


def build_stream_timeline_view(
    events: list[AnalysisStreamEvent],
    *,
    now_iso: str | None = None,
) -> dict[str, Any]:
    stage_order: list[str] = []
    stage_map: dict[str, dict[str, Any]] = {}
    run_started_at: str | None = None
    total_duration_ms: int | None = None
    run_status = "idle"
    current_time = now_iso or _utc_now_iso()

    for event in events:
        if event.event_type == "run_started":
            run_started_at = event.started_at
            run_status = "running"
        elif event.event_type == "run_finished":
            total_duration_ms = event.duration_ms
            run_status = event.status or "success"
        elif event.event_type == "error" and not event.stage_name:
            run_status = "failed"

        if not event.stage_name:
            continue
        if event.stage_name not in stage_map:
            stage_order.append(event.stage_name)
            stage_map[event.stage_name] = {
                "stage_name": event.stage_name,
                "label": STAGE_LABELS.get(
                    event.stage_name,
                    event.stage_name.replace("_", " "),
                ),
                "status": "pending",
                "message": "",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
            }

        stage_entry = stage_map[event.stage_name]
        stage_entry["status"] = event.status or stage_entry["status"]
        stage_entry["message"] = event.message or stage_entry["message"]
        if event.started_at is not None:
            stage_entry["started_at"] = event.started_at
        if event.finished_at is not None:
            stage_entry["finished_at"] = event.finished_at
        if event.duration_ms is not None:
            stage_entry["duration_ms"] = event.duration_ms

    stages: list[dict[str, Any]] = []
    current_stage = ""
    completed_count = 0
    for stage_name in stage_order:
        stage_entry = dict(stage_map[stage_name])
        if stage_entry["duration_ms"] is None and stage_entry["started_at"] is not None:
            stage_entry["duration_ms"] = _duration_between(
                stage_entry["started_at"],
                current_time,
            )
        if stage_entry["status"] == "running" and not current_stage:
            current_stage = stage_name
        if stage_entry["status"] not in {"pending", "running"}:
            completed_count += 1
        stages.append(stage_entry)

    if total_duration_ms is None and run_started_at is not None:
        total_duration_ms = _duration_between(run_started_at, current_time)

    return {
        "stages": stages,
        "current_stage": current_stage,
        "completed_count": completed_count,
        "run_status": run_status,
        "total_duration_ms": total_duration_ms,
    }


def _render_stream_timeline(
    placeholder,
    events: list[AnalysisStreamEvent],
) -> None:
    timeline = build_stream_timeline_view(events)
    status_icon = {
        "success": "ok",
        "completed": "ok",
        "running": "run",
        "failed": "fail",
        "partial": "warn",
        "degraded": "warn",
        "pending": "wait",
    }
    current_stage = timeline["current_stage"]
    with placeholder.container():
        st.markdown("**Execution timeline**")
        if current_stage:
            st.caption(
                f"Current stage: {STAGE_LABELS.get(current_stage, current_stage)}"
            )
        if timeline["total_duration_ms"] is not None:
            st.caption(
                f"Total elapsed: {_format_duration_ms(timeline['total_duration_ms'])}"
            )
        if not timeline["stages"]:
            st.caption("Waiting for backend events...")
        for item in timeline["stages"]:
            icon = status_icon.get(item["status"], item["status"])
            stage_window = _format_stage_window(
                item["started_at"],
                item["finished_at"],
            )
            st.write(
                f"- `{item['label']}` [{icon}] "
                f"{_format_duration_ms(item['duration_ms'])} "
                f"{stage_window} {item['message']}"
            )


def _render_report_blocks(report_blocks: list[dict[str, object]]) -> None:
    if not report_blocks:
        return
    st.markdown("**Detailed result**")
    for block in report_blocks:
        title = str(block.get("title") or block.get("block_type") or "Result block")
        with st.expander(title, expanded=True):
            items = list(block.get("items") or [])
            if not items:
                st.caption("No details")
                continue
            for item in items:
                company_name = str(item.get("company_name") or "").strip()
                doc_type = str(item.get("doc_type") or "").strip()
                excerpt = str(item.get("excerpt") or "").strip()
                prefix = " / ".join(
                    piece for piece in (company_name, doc_type) if piece
                )
                if prefix:
                    st.markdown(f"- **{prefix}**: {excerpt}")
                else:
                    st.markdown(f"- {excerpt}")


def _render_response_details(view: dict[str, object]) -> None:
    answer_markdown = str(view.get("answer_markdown") or "").strip()
    if answer_markdown:
        st.markdown(answer_markdown)
    else:
        st.markdown(f"**Final response:** {view['summary']}")
    _render_report_blocks(list(view.get("report_blocks") or []))

    uncertainty_notes = list(view.get("uncertainty_notes") or [])
    if uncertainty_notes:
        st.markdown("**Uncertainty notes**")
        for note in uncertainty_notes:
            st.write(f"- {note}")

    next_actions = list(view.get("next_actions") or [])
    if next_actions:
        st.markdown("**Suggested next actions**")
        for action in next_actions:
            st.write(f"- {action}")

    if view.get("notes"):
        st.caption(str(view["notes"]))


def _render_response_preview(placeholder, envelope: AnalysisResponseEnvelope | None) -> None:
    with placeholder.container():
        st.markdown("**Final response**")
        if envelope is None:
            st.caption("Waiting for final response...")
            return
        _render_response_details(build_analysis_view_model(envelope))


def _run_request_with_stream(
    client: WorkbenchApiClient,
    *,
    query: str,
    session_id: str | None,
    include_trace: bool,
) -> tuple[AnalysisResponseEnvelope, list[AnalysisStreamEvent]]:
    timeline_placeholder = st.empty()
    answer_placeholder = st.empty()
    queue: Queue[tuple[str, object]] = Queue()
    events: list[AnalysisStreamEvent] = []
    result_holder: dict[str, AnalysisResponseEnvelope | None] = {"envelope": None}
    error_holder: dict[str, str | None] = {"message": None}

    def _worker() -> None:
        try:
            for event in client.stream_request(
                query=query,
                session_id=session_id,
                include_trace=include_trace,
            ):
                queue.put(("event", event))
        except Exception as exc:  # noqa: BLE001
            queue.put(("error", str(exc)))
        finally:
            queue.put(("done", None))

    Thread(target=_worker, daemon=True).start()

    finished = False
    while not finished:
        drained = False
        while True:
            try:
                kind, payload = queue.get_nowait()
            except Empty:
                break
            drained = True
            if kind == "event":
                event = payload
                assert isinstance(event, AnalysisStreamEvent)
                events.append(event)
                envelope = client.extract_envelope_from_stream_event(event)
                if envelope is not None:
                    result_holder["envelope"] = envelope
            elif kind == "error":
                error_holder["message"] = str(payload)
            elif kind == "done":
                finished = True
        _render_stream_timeline(timeline_placeholder, events)
        _render_response_preview(answer_placeholder, result_holder["envelope"])
        if not finished or drained:
            time.sleep(0.2)

    if error_holder["message"]:
        raise RuntimeError(error_holder["message"])
    envelope = result_holder["envelope"]
    if envelope is None:
        raise RuntimeError("stream ended without a final response payload")
    return envelope, events


def render_analysis_view(client: WorkbenchApiClient) -> None:
    st.subheader("Analysis")
    with st.form("analysis_run_form", clear_on_submit=False):
        query = st.text_area("User query", value="", key="analysis_query")
        session_id = st.text_input(
            "Session id (optional for follow-up)",
            value="",
            key="analysis_session_id",
        )
        include_trace = st.checkbox(
            "Include trace",
            value=True,
            key="analysis_include_trace",
        )
        submitted = st.form_submit_button("Run analysis")

    if submitted and query.strip():
        try:
            envelope, events = _run_request_with_stream(
                client,
                query=query.strip(),
                session_id=session_id.strip() or None,
                include_trace=include_trace,
            )
            set_last_analysis_result(st.session_state, envelope)
            st.session_state["_last_analysis_stream_events"] = events
            st.session_state["_last_analysis_error"] = None
        except Exception as exc:  # noqa: BLE001
            st.session_state["_last_analysis_error"] = str(exc)
            st.error(f"Backend request failed: {exc}")

    error_msg = st.session_state.get("_last_analysis_error")
    if error_msg:
        st.warning(f"Last request failed: {error_msg}")

    envelope = get_last_analysis_result(st.session_state)
    if envelope is not None:
        events = list(st.session_state.get("_last_analysis_stream_events") or [])
        if events:
            _render_stream_timeline(st.container(), events)

        view = build_analysis_view_model(envelope)
        card = build_response_summary_card_data(envelope)
        st.markdown(f"**Session id:** `{card['session_id']}`")
        st.markdown(f"**Response type:** `{card['response_type']}`")
        st.markdown(
            f"**Intent:** `{view['intent']}`  "
            f"**Strategy:** `{view['strategy']}`  "
            f"**Evidence refs:** {view['evidence_ref_count']}"
        )
        _render_response_details(view)
        if view["degraded"]:
            st.warning("The latest result is degraded. Please review the timeline and traces.")


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _duration_between(started_at: str, finished_at: str) -> int:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    return max(0, int((finished - started).total_seconds() * 1000))


def _format_duration_ms(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "--"
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.2f}s"
    return f"{duration_ms}ms"


def _format_stage_window(
    started_at: str | None,
    finished_at: str | None,
) -> str:
    start_text = _format_clock(started_at)
    finish_text = _format_clock(finished_at)
    if start_text and finish_text:
        return f"({start_text} -> {finish_text})"
    if start_text:
        return f"(started {start_text})"
    return ""


def _format_clock(value: str | None) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%H:%M:%S")
