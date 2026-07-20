from __future__ import annotations

from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Thread
import html
import re
import time
from typing import Any

import streamlit as st

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.state.workbench_state import (
    get_last_analysis_result,
    set_last_analysis_result,
)
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.analysis_stream_event import AnalysisStreamEvent
from shared.contracts.evidence_detail import SOURCE_TYPE_LABELS


STAGE_LABELS = {
    "routing": "路由分发",
    "stage_planning": "阶段规划",
    "collect_event_context": "事件上下文",
    "analyze_targets": "目标分析",
    "rerank": "重排序",
    "retrieve_evidence": "证据检索",
    "query_structured_data": "结构化数据查询",
    "synthesize_brief_answer": "简答合成",
    "synthesize_event_answer": "事件回答合成",
    "synthesize_report": "报告合成",
    "synthesize_answer": "回答合成",
}

STAGE_ICONS = {
    "routing": "◎",
    "stage_planning": "▦",
    "collect_event_context": "◈",
    "analyze_targets": "◆",
    "rerank": "↕",
    "retrieve_evidence": "⌕",
    "query_structured_data": "▱",
    "synthesize_brief_answer": "✦",
    "synthesize_event_answer": "✦",
    "synthesize_report": "✦",
    "synthesize_answer": "✦",
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
        "evidence_index": dict(getattr(envelope, "evidence_index", None) or {}),
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
                "icon": STAGE_ICONS.get(event.stage_name, "•"),
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


def _render_stage_card_html(item: dict[str, Any]) -> str:
    """渲染单个 stage 卡片为 HTML。"""
    status = item.get("status", "pending")
    label = item.get("label", "")
    icon = item.get("icon", "•")
    duration = _format_duration_ms(item.get("duration_ms"))
    message = item.get("message", "")
    stage_window = _format_stage_window(item.get("started_at"), item.get("finished_at"))

    status_labels = {
        "success": "完成",
        "completed": "完成",
        "running": "运行中",
        "failed": "失败",
        "partial": "部分",
        "degraded": "降级",
        "pending": "等待",
    }
    status_label = status_labels.get(status, status)

    return f"""
    <div class="fs-stage-card fs-status-{status}">
        <div class="fs-stage-header">
            <div class="fs-stage-name">{icon}&nbsp;&nbsp;{label}</div>
            <div class="fs-stage-meta">
                <span>{duration}</span>
                <span>{stage_window}</span>
                <span class="fs-stage-status fs-status-badge-{status}">{status_label}</span>
            </div>
        </div>
        {f'<div class="fs-stage-body">{message}</div>' if message else ''}
    </div>
    """


def _render_stream_timeline(
    placeholder,
    events: list[AnalysisStreamEvent],
) -> None:
    timeline = build_stream_timeline_view(events)
    current_stage = timeline["current_stage"]
    total_ms = timeline["total_duration_ms"]
    completed = timeline["completed_count"]
    total_stages = len(timeline["stages"])

    with placeholder.container():
        # 顶部摘要
        cols = st.columns([1, 1, 1, 1])
        with cols[0]:
            st.markdown(
                f'<div class="fs-section-title">执行进度</div>',
                unsafe_allow_html=True,
            )
        progress_pct = int(completed / total_stages * 100) if total_stages > 0 else 0
        st.markdown(
            f'<div class="fs-progress-track"><div class="fs-progress-bar" style="width: {progress_pct}%"></div></div>',
            unsafe_allow_html=True,
        )

        meta_cols = st.columns(4)
        with meta_cols[0]:
            st.markdown(
                f'<div style="font-family: JetBrains Mono; font-size: 11px; color: var(--fs-text-faint); text-transform: uppercase; letter-spacing: 0.1em;">当前阶段</div>'
                f'<div style="font-family: JetBrains Mono; font-size: 14px; color: var(--fs-accent); font-weight: 600;">{STAGE_LABELS.get(current_stage, "—") if current_stage else "—"}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[1]:
            st.markdown(
                f'<div style="font-family: JetBrains Mono; font-size: 11px; color: var(--fs-text-faint); text-transform: uppercase; letter-spacing: 0.1em;">已完成</div>'
                f'<div style="font-family: JetBrains Mono; font-size: 14px; color: var(--fs-text); font-weight: 600;">{completed} / {total_stages}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[2]:
            st.markdown(
                f'<div style="font-family: JetBrains Mono; font-size: 11px; color: var(--fs-text-faint); text-transform: uppercase; letter-spacing: 0.1em;">总耗时</div>'
                f'<div style="font-family: JetBrains Mono; font-size: 14px; color: var(--fs-text); font-weight: 600;">{_format_duration_ms(total_ms)}</div>',
                unsafe_allow_html=True,
            )
        with meta_cols[3]:
            run_status = timeline["run_status"]
            status_colors = {"running": "var(--fs-accent)", "success": "var(--fs-success)", "failed": "var(--fs-error)", "idle": "var(--fs-text-faint)"}
            st.markdown(
                f'<div style="font-family: JetBrains Mono; font-size: 11px; color: var(--fs-text-faint); text-transform: uppercase; letter-spacing: 0.1em;">运行状态</div>'
                f'<div style="font-family: JetBrains Mono; font-size: 14px; color: {status_colors.get(run_status, "var(--fs-text)")}; font-weight: 600;">{run_status}</div>',
                unsafe_allow_html=True,
            )

        # stage 卡片列表
        if not timeline["stages"]:
            st.caption("等待后端事件...")
        else:
            cards_html = "".join(_render_stage_card_html(s) for s in timeline["stages"])
            st.markdown(cards_html, unsafe_allow_html=True)


def _render_structured_data_result(key_outputs: dict[str, Any]) -> None:
    """渲染结构化数据查询结果（命中/未命中的醒目展示）。"""
    if not key_outputs:
        return

    company = key_outputs.get("company", "")
    metric = key_outputs.get("metric", "")
    value = key_outputs.get("value", "")
    unit = key_outputs.get("unit", "")
    time_scope = key_outputs.get("time_scope", "")
    is_degraded = key_outputs.get("is_degraded", True)
    matched_by = key_outputs.get("matched_by", "")
    source_summary = key_outputs.get("source_summary", "")
    confidence = key_outputs.get("confidence", "")

    if not is_degraded and value:
        # 命中
        st.markdown(
            f"""
            <div class="fs-metric-hit">
                <div class="fs-metric-label">结构化数据 · 命中</div>
                <div class="fs-metric-value">{value} {unit}</div>
                <div class="fs-metric-source">
                    公司: {company} &nbsp;|&nbsp; 指标: {metric} &nbsp;|&nbsp; 期间: {time_scope} &nbsp;|&nbsp; 匹配方式: {matched_by} &nbsp;|&nbsp; 置信度: {confidence}
                </div>
                {f'<div class="fs-metric-source">{source_summary}</div>' if source_summary else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # 未命中
        st.markdown(
            f"""
            <div class="fs-metric-miss">
                <div class="fs-metric-label">结构化数据 · 未命中</div>
                <div class="fs-metric-value-miss">未找到匹配的结构化数据</div>
                <div class="fs-metric-source">
                    公司: {company} &nbsp;|&nbsp; 指标: {metric} &nbsp;|&nbsp; 期间: {time_scope}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_stage_details(envelope: AnalysisResponseEnvelope) -> None:
    """渲染每个 stage 的详细输出（基于 trace_blocks）。"""
    st.markdown('<div class="fs-section-title">中间步骤详情</div>', unsafe_allow_html=True)

    evidence_index = dict(getattr(envelope, "evidence_index", None) or {})

    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            _render_routing_block(block)
        elif block.block_type == "stage_planning":
            _render_stage_planning_block(block)
        elif block.block_type == "execution":
            _render_execution_block(block, evidence_index=evidence_index)


def _render_routing_block(block) -> None:
    """渲染路由结果。"""
    payload = block.payload_summary
    intent = payload.get("intent", "")
    follow_up = payload.get("follow_up_type", "")
    query_mode = payload.get("query_mode", "")

    st.markdown(
        f"""
        <div class="fs-stage-card fs-status-success">
            <div class="fs-stage-header">
                <div class="fs-stage-name">◎&nbsp;&nbsp;路由分发</div>
                <div class="fs-stage-meta">
                    <span class="fs-stage-status fs-status-badge-success">完成</span>
                </div>
            </div>
            <div class="fs-stage-body">
                <div class="fs-kv"><span class="fs-kv-key">Intent</span><span class="fs-kv-val">{intent}</span></div>
                <div class="fs-kv"><span class="fs-kv-key">Follow-up</span><span class="fs-kv-val">{follow_up}</span></div>
                <div class="fs-kv"><span class="fs-kv-key">Query Mode</span><span class="fs-kv-val">{query_mode}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stage_planning_block(block) -> None:
    """渲染阶段规划。"""
    payload = block.payload_summary
    stages = payload.get("stages", [])
    response_mode = payload.get("response_mode", "")
    stage_count = payload.get("stage_count", 0)

    stages_text = " → ".join(stages) if stages else "—"

    st.markdown(
        f"""
        <div class="fs-stage-card fs-status-success">
            <div class="fs-stage-header">
                <div class="fs-stage-name">▦&nbsp;&nbsp;阶段规划</div>
                <div class="fs-stage-meta">
                    <span class="fs-stage-status fs-status-badge-success">完成</span>
                </div>
            </div>
            <div class="fs-stage-body">
                <div class="fs-kv"><span class="fs-kv-key">Response Mode</span><span class="fs-kv-val">{response_mode}</span></div>
                <div class="fs-kv"><span class="fs-kv-key">Stage Count</span><span class="fs-kv-val">{stage_count}</span></div>
                <div class="fs-kv"><span class="fs-kv-key">Pipeline</span><span class="fs-kv-val">{stages_text}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_execution_block(block, evidence_index: dict[str, Any] | None = None) -> None:
    """渲染执行结果——每个 stage 一个卡片。"""
    payload = block.payload_summary
    observations = payload.get("stage_observations", [])
    evidence_index = evidence_index or {}

    for obs in observations:
        stage_name = obs.get("stage_name", "")
        status = obs.get("status", "pending")
        key_outputs = obs.get("key_outputs", {})
        evidence_refs = obs.get("evidence_refs", [])

        label = STAGE_LABELS.get(stage_name, stage_name.replace("_", " "))
        icon = STAGE_ICONS.get(stage_name, "•")
        status_labels = {
            "success": "完成", "completed": "完成", "running": "运行中",
            "failed": "失败", "partial": "部分", "degraded": "降级", "pending": "等待",
        }
        status_label = status_labels.get(status, status)

        # 构建 key_outputs 展示
        kv_html = ""
        if key_outputs:
            for k, v in key_outputs.items():
                if k in ("company", "metric", "value", "unit", "time_scope", "is_degraded",
                         "matched_by", "source_summary", "confidence"):
                    continue  # 这些字段在结构化数据卡片里单独展示
                v_str = str(v) if v is not None else ""
                if len(v_str) > 150:
                    v_str = v_str[:150] + "..."
                kv_html += f'<div class="fs-kv"><span class="fs-kv-key">{k}</span><span class="fs-kv-val">{v_str}</span></div>'

        # 证据引用：从 evidence_index 解析出来源标注（不再只显示「N 条」）
        evidence_html = ""
        if evidence_refs:
            rows = []
            for i, ref in enumerate(evidence_refs, 1):
                detail = evidence_index.get(ref)
                if detail:
                    rows.append(_render_evidence_inline(i, detail))
                else:
                    rows.append(
                        f'<div class="fs-evidence-inline">'
                        f'<span class="fs-evidence-inline-idx">{i}</span>'
                        f'<span class="fs-evidence-inline-body">{html.escape(str(ref))}</span>'
                        f'</div>'
                    )
            evidence_html = (
                f'<div class="fs-kv"><span class="fs-kv-key">Evidence</span>'
                f'<span class="fs-kv-val">{len(evidence_refs)} 条</span></div>'
                + "".join(rows)
            )

        st.markdown(
            f"""
            <div class="fs-stage-card fs-status-{status}">
                <div class="fs-stage-header">
                    <div class="fs-stage-name">{icon}&nbsp;&nbsp;{label}</div>
                    <div class="fs-stage-meta">
                        <span class="fs-stage-status fs-status-badge-{status}">{status_label}</span>
                    </div>
                </div>
                <div class="fs-stage-body">
                    {kv_html}
                    {evidence_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 结构化数据查询结果特别展示
        if stage_name == "query_structured_data":
            _render_structured_data_result(key_outputs)


def _render_report_blocks(report_blocks: list[dict[str, object]]) -> None:
    if not report_blocks:
        return
    st.markdown('<div class="fs-section-title">详细报告</div>', unsafe_allow_html=True)
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


def _evidence_badge(source_type: str) -> str:
    """来源类型徽章（HTML）。"""
    label = SOURCE_TYPE_LABELS.get(source_type, source_type)
    return (
        f'<span class="fs-evidence-badge fs-evidence-badge-{html.escape(source_type)}">'
        f'{html.escape(label)}</span>'
    )


def _evidence_meta_line(d: dict[str, Any]) -> str:
    """按 source_type 拼出来源标注的元信息行。"""
    source_type = d.get("source_type", "")
    parts: list[str] = []
    if source_type in ("annual_report", "filing"):
        doc_type = str(d.get("doc_type") or "")
        year = str(d.get("report_year") or "")
        section = " / ".join(
            str(s) for s in (d.get("section_path") or []) if str(s).strip()
        )
        pages = str(d.get("pages") or "")
        if doc_type:
            parts.append(html.escape(doc_type))
        if year:
            parts.append(html.escape(year))
        if section:
            parts.append(html.escape(section))
        if pages:
            parts.append(f"p{html.escape(pages)}")
    elif source_type == "news":
        src = str(d.get("source") or "")
        date = str(d.get("publish_date") or "")
        if src:
            parts.append(html.escape(src))
        if date:
            parts.append(html.escape(date))
    elif source_type == "structured_metric":
        metric = str(d.get("metric") or "")
        value = str(d.get("value") or "")
        unit = str(d.get("unit") or "")
        period = str(d.get("period") or "")
        if metric:
            parts.append(html.escape(metric))
        if value:
            parts.append(html.escape(f"{value} {unit}".strip()))
        if period:
            parts.append(html.escape(period))
        matched = str(d.get("matched_by") or "")
        if matched:
            parts.append(f"匹配:{html.escape(matched)}")
    return f'<span class="fs-evidence-sep">·</span>'.join(parts)


def _render_evidence_card(d: dict[str, Any]) -> str:
    """单条证据的来源标注卡片（参考来源面板用）。"""
    source_type = d.get("source_type", "")
    company = html.escape(str(d.get("company_name") or ""))
    code = html.escape(str(d.get("company_code") or ""))
    badge = _evidence_badge(source_type)

    head_parts: list[str] = []
    if company:
        head_parts.append(f'<span class="fs-evidence-company">{company}</span>')
    if code:
        head_parts.append(f'<span class="fs-evidence-code">{code}</span>')
    if head_parts:
        head = "".join(head_parts)
    else:
        title = html.escape(str(d.get("title") or d.get("evidence_id") or ""))
        head = f'<span class="fs-evidence-company">{title}</span>'

    meta = _evidence_meta_line(d)
    # 归一化 excerpt 空白（含换行）→ 单空格，避免原始文本里的空白行截断 HTML 块
    excerpt = html.escape(re.sub(r"\s+", " ", str(d.get("excerpt") or "")).strip())
    link_html = ""
    url = str(d.get("url") or "")
    if url:
        link_html = (
            f' &nbsp;<a class="fs-evidence-link" href="{html.escape(url)}" '
            f'target="_blank" rel="noopener">原文↗</a>'
        )

    # 注意：必须紧凑无空行——CommonMark 的 <div> HTML 块遇到空白行会结束，
    # 否则卡片之间出现空行会导致后续内容被当成原始文本显示（“html片段”）。
    parts = [
        '<div class="fs-evidence-card">',
        f'<div class="fs-evidence-head">{badge}{head}{link_html}</div>',
        f'<div class="fs-evidence-meta">{meta}</div>',
    ]
    if excerpt:
        parts.append(f'<div class="fs-evidence-excerpt">{excerpt}</div>')
    parts.append("</div>")
    return "".join(parts)


def _render_evidence_inline(i: int, d: dict[str, Any]) -> str:
    """中间节点内单条证据的来源标注行。"""
    source_type = d.get("source_type", "")
    if source_type in ("annual_report", "filing"):
        company = str(d.get("company_name") or "")
        code = str(d.get("company_code") or "")
        doc_type = str(d.get("doc_type") or "")
        pages = str(d.get("pages") or "")
        section = " / ".join(
            str(s) for s in (d.get("section_path") or []) if str(s).strip()
        )
        bits = [b for b in (company, f"({code})" if code else "", doc_type, section,
                             f"p{pages}" if pages else "") if b]
        body = " · ".join(html.escape(b) for b in bits)
    elif source_type == "news":
        title = str(d.get("title") or "")
        src = str(d.get("source") or "")
        date = str(d.get("publish_date") or "")
        url = str(d.get("url") or "")
        body = " · ".join(html.escape(b) for b in (title, src, date) if b)
        if url:
            body += f' &nbsp;<a href="{html.escape(url)}" target="_blank" rel="noopener">↗</a>'
    elif source_type == "structured_metric":
        company = str(d.get("company_name") or "")
        metric = str(d.get("metric") or "")
        value = str(d.get("value") or "")
        unit = str(d.get("unit") or "")
        period = str(d.get("period") or "")
        bits = [b for b in (company, metric, f"{value} {unit}".strip() if value else "",
                             period) if b]
        body = " · ".join(html.escape(b) for b in bits)
    else:
        body = html.escape(str(d.get("evidence_id") or ""))
    return (
        f'<div class="fs-evidence-inline">'
        f'<span class="fs-evidence-inline-idx">{i}</span>'
        f'<span class="fs-evidence-inline-body">{body}</span>'
        f'</div>'
    )


def _render_evidence_sources(evidence_index: dict[str, Any]) -> None:
    """渲染「参考来源」面板：把 evidence_index 按来源类型分组展示来源标注。"""
    if not evidence_index:
        return
    st.markdown(
        '<div class="fs-section-title">参考来源 · 来源标注</div>',
        unsafe_allow_html=True,
    )
    order = {"annual_report": 0, "filing": 1, "structured_metric": 2, "news": 3}
    items = sorted(
        evidence_index.values(),
        key=lambda d: (
            order.get(d.get("source_type", ""), 9),
            str(d.get("company_name") or ""),
            str(d.get("evidence_id") or ""),
        ),
    )
    cards = "".join(_render_evidence_card(d) for d in items)
    # 防御：CommonMark 的 <div> HTML 块遇空白行会截断，压缩掉空白行避免“html片段”
    cards = re.sub(r"\n[ \t]*\n", "\n", cards)
    st.markdown(
        f'<div class="fs-evidence-panel">{cards}</div>',
        unsafe_allow_html=True,
    )


def _render_response_details(view: dict[str, object]) -> None:
    answer_markdown = str(view.get("answer_markdown") or "").strip()

    st.markdown('<div class="fs-section-title">最终回答</div>', unsafe_allow_html=True)

    if answer_markdown:
        st.markdown(
            f'<div class="fs-answer-block"><div class="fs-answer-text">{answer_markdown}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="fs-answer-block"><div class="fs-answer-text">{view["summary"]}</div></div>',
            unsafe_allow_html=True,
        )

    # 参考来源标注（年报 RAG / 事件新闻 / 结构化指标统一溯源）
    _render_evidence_sources(view.get("evidence_index") or {})

    _render_report_blocks(list(view.get("report_blocks") or []))

    uncertainty_notes = list(view.get("uncertainty_notes") or [])
    if uncertainty_notes:
        st.markdown('<div class="fs-section-title">不确定性说明</div>', unsafe_allow_html=True)
        for note in uncertainty_notes:
            st.markdown(f"- {note}")

    next_actions = list(view.get("next_actions") or [])
    if next_actions:
        st.markdown('<div class="fs-section-title">建议后续操作</div>', unsafe_allow_html=True)
        for action in next_actions:
            st.markdown(f"- {action}")


def _render_response_preview(placeholder, envelope: AnalysisResponseEnvelope | None) -> None:
    with placeholder.container():
        if envelope is None:
            return
        view = build_analysis_view_model(envelope)
        _render_response_details(view)


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
    # 查询表单
    st.markdown('<div class="fs-section-title">查询输入</div>', unsafe_allow_html=True)
    with st.form("analysis_run_form", clear_on_submit=False):
        query = st.text_area("User query", value="", key="analysis_query", height=68)
        cols = st.columns([2, 2, 1])
        with cols[0]:
            session_id = st.text_input(
                "Session id (可选, 用于追问)",
                value="",
                key="analysis_session_id",
            )
        with cols[1]:
            include_trace = st.checkbox(
                "包含 Trace (中间步骤)",
                value=True,
                key="analysis_include_trace",
            )
        with cols[2]:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("▶ 执行分析")

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
            # 重新渲染完整结果
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.session_state["_last_analysis_error"] = str(exc)
            st.error(f"后端请求失败: {exc}")

    error_msg = st.session_state.get("_last_analysis_error")
    if error_msg:
        st.warning(f"上次请求失败: {error_msg}")

    envelope = get_last_analysis_result(st.session_state)
    if envelope is not None:
        events = list(st.session_state.get("_last_analysis_stream_events") or [])

        # 顶部摘要
        view = build_analysis_view_model(envelope)
        st.markdown('<div class="fs-section-title">执行摘要</div>', unsafe_allow_html=True)
        summary_cols = st.columns(5)
        with summary_cols[0]:
            _render_summary_metric("Intent", view["intent"])
        with summary_cols[1]:
            _render_summary_metric("Response Type", view["response_type"])
        with summary_cols[2]:
            _render_summary_metric("Strategy", view["strategy"] or "—")
        with summary_cols[3]:
            _render_summary_metric("Evidence Refs", str(view["evidence_ref_count"]))
        with summary_cols[4]:
            _render_summary_metric("Session", str(view["session_id"])[:8] + "..." if view["session_id"] else "—")

        # 执行时间线
        if events:
            st.markdown('<div class="fs-section-title">执行时间线</div>', unsafe_allow_html=True)
            _render_stream_timeline(st.container(), events)

        # 中间步骤详情
        _render_stage_details(envelope)

        # 最终回答
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        _render_response_details(view)

        if view["degraded"]:
            st.warning("⚠ 当前结果为降级状态，请检查时间线和 Trace 详情。")


def _render_summary_metric(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div style="
            background: var(--fs-bg-card);
            border: 1px solid var(--fs-border);
            border-radius: 6px;
            padding: 12px 16px;
        ">
            <div style="font-family: JetBrains Mono; font-size: 10px; color: var(--fs-text-faint); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">{label}</div>
            <div style="font-family: JetBrains Mono; font-size: 13px; color: var(--fs-text); font-weight: 600; word-break: break-all;">{value or '—'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        return "—"
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
        return f"{start_text} → {finish_text}"
    if start_text:
        return f"started {start_text}"
    return ""


def _format_clock(value: str | None) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%H:%M:%S")
