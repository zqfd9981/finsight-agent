"""Chat 风格对话视图。

布局：
- 左侧侧边栏：会话列表（新建/切换/删除）
- 主区域：消息气泡（user/assistant）+ 折叠的执行过程 trace + 底部输入框

复用 analysis_view 的 trace 渲染逻辑（routing/stage_planning/execution 卡片）。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.pages.analysis_view import (
    _render_evidence_inline,
    _render_evidence_sources,
)
from frontend.streamlit_app.state.chat_state import (
    append_assistant_message,
    append_user_message,
    create_new_session,
    delete_session,
    ensure_chat_state,
    get_active_session,
    list_sessions,
    switch_to_session,
)


def render_chat_view(client: WorkbenchApiClient) -> None:
    """渲染 Chat 对话视图。"""
    ensure_chat_state()

    # ── 左侧侧边栏：会话管理 ──
    with st.sidebar:
        st.markdown("### 会话列表")
        if st.button("＋ 新建会话", key="btn_new_session", use_container_width=True):
            create_new_session()
            st.rerun()

        st.markdown('<div class="fs-chat-session-list">', unsafe_allow_html=True)
        sessions = list_sessions()
        if not sessions:
            st.markdown(
                '<div class="fs-chat-empty">暂无会话，点击上方新建</div>',
                unsafe_allow_html=True,
            )
        for sess in sessions:
            sid = sess["session_id"]
            title = sess["title"]
            msg_count = len(sess["messages"])
            col1, col2 = st.columns([5, 1])
            with col1:
                if st.button(
                    title,
                    key=f"sess_btn_{sid}",
                    help=f"{sid} · {msg_count} 条消息",
                    use_container_width=True,
                ):
                    switch_to_session(sid)
                    st.rerun()
            with col2:
                if st.button("×", key=f"sess_del_{sid}", help="删除会话"):
                    delete_session(sid)
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 主区域：对话流 ──
    active = get_active_session()
    if active is None:
        _render_welcome()
        return

    st.markdown(
        f'<div class="fs-chat-header">'
        f'<span class="fs-chat-title">{active["title"]}</span>'
        f'<span class="fs-chat-meta">{active["session_id"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 渲染历史消息
    for idx, msg in enumerate(active["messages"]):
        msg_evidence_index = msg.get("evidence_index") or {}
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("trace_blocks"):
                with st.expander("查看执行过程", expanded=False):
                    _render_trace_blocks(
                        msg["trace_blocks"], evidence_index=msg_evidence_index
                    )
            # 参考来源标注（年报 RAG / 事件新闻 / 结构化指标统一溯源）
            if msg["role"] == "assistant" and msg_evidence_index:
                _render_evidence_sources(msg_evidence_index)

    # 输入框
    if query := st.chat_input("输入你的问题..."):
        _handle_user_input(client, active["session_id"], query)


def _render_welcome() -> None:
    """渲染欢迎页（无活跃会话时）。"""
    st.markdown(
        """
        <div class="fs-chat-welcome">
            <div class="fs-chat-welcome-logo">◈</div>
            <div class="fs-chat-welcome-title">FinSight 对话</div>
            <div class="fs-chat-welcome-sub">
                财务智能体 · 支持多轮追问与指代消解<br/>
                点击左侧"新建会话"开始对话
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _handle_user_input(
    client: WorkbenchApiClient,
    session_id: str,
    query: str,
) -> None:
    """处理用户输入：追加消息 → 调用后端 → 渲染 assistant 回复。"""
    # 判断首轮/追问：消息历史为空则是首轮（尽管已带 session_id，后端尚无记录）
    active = get_active_session()
    has_history = bool(active and active["messages"])
    query_mode = "follow_up" if has_history else "first_turn"

    # 1. 立即渲染 user 消息
    with st.chat_message("user"):
        st.markdown(query)
    append_user_message(session_id, query)

    # 2. 调用后端
    try:
        with st.spinner("思考中..."):
            envelope = client.send_request(
                query=query,
                session_id=session_id,
                include_trace=True,
                query_mode=query_mode,
            )
    except Exception as exc:
        error_msg = f"后端调用失败: {exc}"
        with st.chat_message("assistant"):
            st.error(error_msg)
        append_assistant_message(session_id, error_msg, trace_blocks=[])
        st.rerun()
        return

    # 3. 渲染 assistant 回复
    # 优先用 answer_markdown（reporting service LLM 重写的自然语言），对齐 analysis_view
    response = envelope.response
    answer_markdown = str(getattr(response, "answer_markdown", "") or "").strip()
    summary = str(getattr(response, "summary", "") or "").strip()
    # answer_markdown 非空时用它（更自然），否则 fallback 到 summary
    display_text = answer_markdown or summary
    response_type = getattr(response, "response_type", "success")
    trace_blocks = envelope.trace_blocks or []
    evidence_index = dict(getattr(envelope, "evidence_index", None) or {})
    backend_session_id = envelope.session_id or session_id

    with st.chat_message("assistant"):
        if response_type in {"guardrail", "error"}:
            st.warning(display_text or "请求被拒绝或出错")
        else:
            st.markdown(display_text)
        if trace_blocks:
            with st.expander("查看执行过程", expanded=False):
                _render_trace_blocks(trace_blocks, evidence_index=evidence_index)
        # 参考来源标注（年报 RAG / 事件新闻 / 结构化指标统一溯源）
        if evidence_index:
            _render_evidence_sources(evidence_index)

    append_assistant_message(
        session_id,
        display_text,
        trace_blocks=trace_blocks,
        session_id_from_backend=backend_session_id,
        evidence_index=evidence_index,
    )
    st.rerun()


def _render_trace_blocks(
    trace_blocks: list[Any], evidence_index: dict[str, Any] | None = None
) -> None:
    """渲染 trace_blocks（复用 analysis_view 的卡片样式）。

    为保持 chat_view 独立性，这里内联简化版渲染逻辑，
    样式复用 theme.py 的 fs-stage-card 等 CSS class。
    evidence_index 用于中间节点证据来源的逐条标注。
    """
    evidence_index = evidence_index or {}
    for block in trace_blocks:
        if not hasattr(block, "block_type"):
            continue
        if block.block_type == "routing":
            _render_routing_block(block)
        elif block.block_type == "stage_planning":
            _render_stage_planning_block(block)
        elif block.block_type == "execution":
            _render_execution_block(block, evidence_index=evidence_index)


def _render_routing_block(block: Any) -> None:
    """渲染路由结果卡片。"""
    payload = block.payload_summary or {}
    intent = payload.get("intent", "")
    follow_up = payload.get("follow_up_type", "")
    query_mode = payload.get("query_mode", "")
    st.markdown(
        f"""
        <div class="fs-stage-card fs-status-success">
            <div class="fs-stage-header">
                <div class="fs-stage-name">◎&nbsp;&nbsp;路由分发</div>
                <span class="fs-stage-status fs-status-badge-success">完成</span>
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


def _render_stage_planning_block(block: Any) -> None:
    """渲染阶段规划卡片。"""
    payload = block.payload_summary or {}
    stages = payload.get("stages", [])
    response_mode = payload.get("response_mode", "")
    stages_text = " → ".join(stages) if stages else "—"
    st.markdown(
        f"""
        <div class="fs-stage-card fs-status-success">
            <div class="fs-stage-header">
                <div class="fs-stage-name">▦&nbsp;&nbsp;阶段规划</div>
                <span class="fs-stage-status fs-status-badge-success">完成</span>
            </div>
            <div class="fs-stage-body">
                <div class="fs-kv"><span class="fs-kv-key">Response Mode</span><span class="fs-kv-val">{response_mode}</span></div>
                <div class="fs-kv"><span class="fs-kv-key">Pipeline</span><span class="fs-kv-val">{stages_text}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_execution_block(
    block: Any, evidence_index: dict[str, Any] | None = None
) -> None:
    """渲染执行结果——每个 stage 一个卡片。"""
    payload = block.payload_summary or {}
    observations = payload.get("stage_observations", [])
    evidence_index = evidence_index or {}
    for obs in observations:
        stage_name = obs.get("stage_name", "")
        status = obs.get("status", "pending")
        key_outputs = obs.get("key_outputs", {}) or {}
        message = obs.get("message", "")
        evidence_refs = obs.get("evidence_refs", []) or []

        # query_structured_data 特殊渲染
        if stage_name == "query_structured_data":
            _render_structured_data_card(key_outputs, status)
            continue

        # 通用 stage 卡片
        kv_html = ""
        for k, v in key_outputs.items():
            kv_html += f'<div class="fs-kv"><span class="fs-kv-key">{k}</span><span class="fs-kv-val">{v}</span></div>'

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
                        f'<span class="fs-evidence-inline-body">{ref}</span>'
                        f'</div>'
                    )
            evidence_html = (
                f'<div class="fs-kv"><span class="fs-kv-key">Evidence</span>'
                f'<span class="fs-kv-val">{len(evidence_refs)} 条</span></div>'
                + "".join(rows)
            )

        status_labels = {
            "success": "完成", "completed": "完成", "running": "运行中",
            "failed": "失败", "partial": "部分", "degraded": "降级", "pending": "等待",
        }
        status_label = status_labels.get(status, status)
        st.markdown(
            f"""
            <div class="fs-stage-card fs-status-{status}">
                <div class="fs-stage-header">
                    <div class="fs-stage-name">●&nbsp;&nbsp;{stage_name}</div>
                    <span class="fs-stage-status fs-status-badge-{status}">{status_label}</span>
                </div>
                <div class="fs-stage-body">
                    {kv_html if kv_html else f'<div class="fs-stage-message">{message}</div>'}
                    {evidence_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_structured_data_card(key_outputs: dict, status: str) -> None:
    """渲染 query_structured_data stage 的命中/未命中卡片。"""
    # trace 暴露的是 is_degraded（True=降级/未命中，False=命中），对齐 analysis_view
    is_degraded = key_outputs.get("is_degraded", True)
    company = key_outputs.get("company", "")
    metric = key_outputs.get("metric", "")
    period = key_outputs.get("time_scope", "") or key_outputs.get("period", "")
    value = key_outputs.get("value", "")
    unit = key_outputs.get("unit", "")
    matched_by = key_outputs.get("matched_by", "")
    confidence = key_outputs.get("confidence", "")
    source_summary = key_outputs.get("source_summary", "")

    if not is_degraded and value:
        st.markdown(
            f"""
            <div class="fs-stage-card fs-status-success">
                <div class="fs-stage-header">
                    <div class="fs-stage-name">📊&nbsp;&nbsp;结构化数据命中</div>
                    <span class="fs-stage-status fs-status-badge-success">命中</span>
                </div>
                <div class="fs-stage-body">
                    <div class="fs-structured-value">{value} <span class="fs-structured-unit">{unit}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">公司</span><span class="fs-kv-val">{company}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">指标</span><span class="fs-kv-val">{metric}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">期间</span><span class="fs-kv-val">{period}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">匹配方式</span><span class="fs-kv-val">{matched_by}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">置信度</span><span class="fs-kv-val">{confidence}</span></div>
                    {f'<div class="fs-kv"><span class="fs-kv-key">来源</span><span class="fs-kv-val">{source_summary}</span></div>' if source_summary else ''}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="fs-stage-card fs-status-failed">
                <div class="fs-stage-header">
                    <div class="fs-stage-name">📊&nbsp;&nbsp;结构化数据未命中</div>
                    <span class="fs-stage-status fs-status-badge-failed">未命中</span>
                </div>
                <div class="fs-stage-body">
                    <div class="fs-kv"><span class="fs-kv-key">公司</span><span class="fs-kv-val">{company or "—"}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">指标</span><span class="fs-kv-val">{metric or "—"}</span></div>
                    <div class="fs-kv"><span class="fs-kv-key">期间</span><span class="fs-kv-val">{period or "—"}</span></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
