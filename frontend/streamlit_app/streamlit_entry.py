"""Streamlit 工作台入口。

被 ``streamlit run frontend/streamlit_app/streamlit_entry.py`` 直接调用。
模块顶层执行 ``bootstrap_streamlit_app``；在非 Streamlit runtime 下
(例如单元测试的 import) 会捕获异常并继续，让模块自身可被外部 import。
"""

from __future__ import annotations

import logging

import streamlit as st

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.pages.analysis_view import render_analysis_view
from frontend.streamlit_app.pages.debug_view import render_debug_view
from frontend.streamlit_app.pages.eval_view import render_eval_view
from frontend.streamlit_app.theme import inject_theme


PAGE_ANALYSIS = "分析视图"
PAGE_DEBUG = "调试视图"
PAGE_EVAL = "评测视图"


def bootstrap_streamlit_app() -> None:
    """组装 set_page_config + 侧边栏页面选择 + 渲染分发。"""

    # set_page_config 必须是首个 st.* 调用；保持它在函数体内最顶部。
    st.set_page_config(
        page_title="FinSight Workbench",
        page_icon="◈",
        layout="wide",
    )
    inject_theme()
    client = WorkbenchApiClient()

    st.markdown(
        '<div class="fs-app-header">'
        '<span class="fs-app-logo">◈</span>'
        '<span class="fs-app-title">FinSight Workbench</span>'
        '<span class="fs-app-sub">财务智能体 · 中间步骤可视化</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    choice = st.sidebar.radio("页面", [PAGE_ANALYSIS, PAGE_DEBUG, PAGE_EVAL])

    if choice == PAGE_ANALYSIS:
        render_analysis_view(client)
    elif choice == PAGE_DEBUG:
        render_debug_view()
    else:
        render_eval_view(client)


# Streamlit 通过 exec() 跑本模块，所以顶层调用是规范做法；
# 单元测试 import 时没有 Streamlit runtime，捕获后只记日志即可。
try:
    bootstrap_streamlit_app()
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).debug(
        "streamlit_entry loaded outside Streamlit runtime; bootstrap skipped: %s",
        exc,
    )
