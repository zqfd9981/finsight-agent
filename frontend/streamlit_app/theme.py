"""FinSight Workbench 暗色金融终端主题。

美学定位：Bloomberg Terminal 的克制 + Linear/Vercel 暗色 UI 的现代化。
- 深色背景（炭黑 #0a0e14）+ 单一强调色（琥珀金 #e8b057）
- 等宽字体（JetBrains Mono）显示数据，无衬线字体显示标签
- 每个 stage 一个卡片，命中=翠绿，未命中=暗红
"""

from __future__ import annotations

import streamlit as st


_THEME_CSS = """
<style>
/* ===== 字体导入 ===== */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Manrope:wght@300;400;500;600;700;800&family=Noto+Serif+SC:wght@400;600;700&display=swap');

/* ===== 根变量 ===== */
:root {
    --fs-bg: #0a0e14;
    --fs-bg-elevated: #131820;
    --fs-bg-card: #1a212c;
    --fs-bg-hover: #232b38;
    --fs-border: #2a3344;
    --fs-border-bright: #3a4658;
    --fs-text: #e6edf3;
    --fs-text-dim: #8b98a9;
    --fs-text-faint: #5a6573;
    --fs-accent: #e8b057;
    --fs-accent-dim: #b8893a;
    --fs-success: #4ade80;
    --fs-success-bg: rgba(74, 222, 128, 0.08);
    --fs-error: #f87171;
    --fs-error-bg: rgba(248, 113, 113, 0.08);
    --fs-warning: #fbbf24;
    --fs-warning-bg: rgba(251, 191, 36, 0.08);
    --fs-info: #60a5fa;
    --fs-info-bg: rgba(96, 165, 250, 0.08);
}

/* ===== 全局背景 ===== */
.stApp {
    background: var(--fs-bg) !important;
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(232, 176, 87, 0.06), transparent),
        radial-gradient(ellipse 60% 40% at 80% 100%, rgba(96, 165, 250, 0.04), transparent) !important;
    font-family: 'Manrope', -apple-system, sans-serif !important;
    color: var(--fs-text) !important;
}

/* ===== 隐藏默认 Streamlit 元素 ===== */
#MainMenu, footer, header[data-testid="stHeader"] {
    display: none !important;
}

/* ===== 应用标题 ===== */
.fs-app-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 20px 0 28px 0;
    border-bottom: 1px solid var(--fs-border);
    margin-bottom: 24px;
}
.fs-app-logo {
    font-size: 28px;
    color: var(--fs-accent);
    font-weight: 700;
    line-height: 1;
}
.fs-app-title {
    font-family: 'Manrope', sans-serif;
    font-size: 24px;
    font-weight: 800;
    color: var(--fs-text);
    letter-spacing: -0.02em;
}
.fs-app-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fs-text-faint);
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-left: auto;
}

/* ===== 侧边栏 ===== */
section[data-testid="stSidebar"] {
    background: var(--fs-bg-elevated) !important;
    border-right: 1px solid var(--fs-border) !important;
}
section[data-testid="stSidebar"] .stRadio > label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: var(--fs-text-dim) !important;
}

/* ===== 通用文本 ===== */
h1, h2, h3, h4 {
    font-family: 'Manrope', sans-serif !important;
    color: var(--fs-text) !important;
    letter-spacing: -0.02em !important;
}
p, li, span {
    color: var(--fs-text) !important;
}

/* ===== 区块标题 ===== */
.fs-section-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--fs-text-faint);
    padding: 16px 0 12px 0;
    border-bottom: 1px solid var(--fs-border);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.fs-section-title::before {
    content: "";
    width: 3px;
    height: 12px;
    background: var(--fs-accent);
}

/* ===== 查询输入框 ===== */
.stTextArea > div > div > textarea,
.stTextInput > div > div > input {
    background: var(--fs-bg-elevated) !important;
    border: 1px solid var(--fs-border) !important;
    border-radius: 6px !important;
    color: var(--fs-text) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 14px !important;
}
.stTextArea > div > div > textarea:focus,
.stTextInput > div > div > input:focus {
    border-color: var(--fs-accent) !important;
    box-shadow: 0 0 0 3px rgba(232, 176, 87, 0.1) !important;
}
.stTextArea > label, .stTextInput > label, .stCheckbox > label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: var(--fs-text-dim) !important;
}

/* ===== 按钮 ===== */
.stButton > button {
    background: var(--fs-accent) !important;
    color: var(--fs-bg) !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em !important;
    padding: 10px 24px !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: #f0c06a !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(232, 176, 87, 0.2) !important;
}

/* ===== Stage 卡片 ===== */
.fs-stage-card {
    background: var(--fs-bg-card);
    border: 1px solid var(--fs-border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s ease;
}
.fs-stage-card::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
}
.fs-stage-card.fs-status-success::before { background: var(--fs-success); }
.fs-stage-card.fs-status-failed::before { background: var(--fs-error); }
.fs-stage-card.fs-status-running::before {
    background: var(--fs-accent);
    animation: pulse 1.2s ease-in-out infinite;
}
.fs-stage-card.fs-status-pending::before { background: var(--fs-text-faint); }
.fs-stage-card.fs-status-degraded::before { background: var(--fs-warning); }

@keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 1; }
}

.fs-stage-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}
.fs-stage-name {
    font-family: 'Manrope', sans-serif;
    font-size: 15px;
    font-weight: 700;
    color: var(--fs-text);
}
.fs-stage-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fs-text-faint);
}
.fs-stage-status {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 3px 8px;
    border-radius: 4px;
}
.fs-status-badge-success { background: var(--fs-success-bg); color: var(--fs-success); }
.fs-status-badge-failed { background: var(--fs-error-bg); color: var(--fs-error); }
.fs-status-badge-running { background: rgba(232, 176, 87, 0.1); color: var(--fs-accent); }
.fs-status-badge-pending { background: rgba(138, 152, 169, 0.1); color: var(--fs-text-faint); }
.fs-status-badge-degraded { background: var(--fs-warning-bg); color: var(--fs-warning); }

.fs-stage-body {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--fs-text-dim);
    line-height: 1.7;
}
.fs-stage-body .fs-kv {
    display: flex;
    gap: 8px;
    padding: 2px 0;
}
.fs-stage-body .fs-kv-key {
    color: var(--fs-text-faint);
    min-width: 100px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 10px;
    padding-top: 2px;
}
.fs-stage-body .fs-kv-val {
    color: var(--fs-text);
    flex: 1;
    word-break: break-word;
}

/* ===== 结构化数据命中展示 ===== */
.fs-metric-hit {
    background: var(--fs-success-bg);
    border: 1px solid rgba(74, 222, 128, 0.2);
    border-radius: 6px;
    padding: 12px 16px;
    margin-top: 10px;
}
.fs-metric-miss {
    background: var(--fs-error-bg);
    border: 1px solid rgba(248, 113, 113, 0.2);
    border-radius: 6px;
    padding: 12px 16px;
    margin-top: 10px;
}
.fs-metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: var(--fs-success);
    letter-spacing: -0.02em;
}
.fs-metric-value-miss {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 600;
    color: var(--fs-error);
}
.fs-metric-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fs-text-faint);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 4px;
}
.fs-metric-source {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fs-text-faint);
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
}

/* ===== 最终答案 ===== */
.fs-answer-block {
    background: var(--fs-bg-card);
    border: 1px solid var(--fs-border);
    border-radius: 8px;
    padding: 24px 28px;
    margin-top: 16px;
    position: relative;
}
.fs-answer-block::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--fs-accent);
}
.fs-answer-text {
    font-family: 'Noto Serif SC', serif;
    font-size: 15px;
    line-height: 1.8;
    color: var(--fs-text);
}

/* ===== 时间线进度条 ===== */
.fs-progress-track {
    height: 2px;
    background: var(--fs-border);
    border-radius: 1px;
    overflow: hidden;
    margin: 8px 0 16px 0;
}
.fs-progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--fs-accent), var(--fs-accent-dim));
    border-radius: 1px;
    transition: width 0.3s ease;
}

/* ===== Expander 自定义 ===== */
details {
    background: var(--fs-bg-elevated) !important;
    border: 1px solid var(--fs-border) !important;
    border-radius: 6px !important;
}
summary {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: var(--fs-text-dim) !important;
}

/* ===== JSON 展示 ===== */
.stJson {
    background: var(--fs-bg-elevated) !important;
    border: 1px solid var(--fs-border) !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
}

/* ===== 警告/错误提示 ===== */
.stAlert {
    border-radius: 6px !important;
}

/* ===== 表格 ===== */
.stDataFrame {
    font-family: 'JetBrains Mono', monospace !important;
}
.stDataFrame table {
    background: var(--fs-bg-elevated) !important;
}

/* ===== 滚动条 ===== */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: var(--fs-bg);
}
::-webkit-scrollbar-thumb {
    background: var(--fs-border-bright);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--fs-text-faint);
}

/* ===== 分隔线 ===== */
hr {
    border-color: var(--fs-border) !important;
    margin: 24px 0 !important;
}

/* ===== Caption ===== */
.stMarkdown p {
    font-size: 13px;
    line-height: 1.6;
}

/* ── Chat 视图专属样式 ── */
.fs-chat-welcome {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 20px;
    text-align: center;
}
.fs-chat-welcome-logo {
    font-size: 48px;
    color: var(--fs-accent);
    margin-bottom: 16px;
}
.fs-chat-welcome-title {
    font-family: 'Manrope', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--fs-text);
    margin-bottom: 12px;
}
.fs-chat-welcome-sub {
    font-family: 'Manrope', sans-serif;
    font-size: 14px;
    color: var(--fs-text-faint);
    line-height: 1.6;
}

.fs-chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    margin-bottom: 16px;
    border-bottom: 1px solid rgba(232, 176, 87, 0.15);
}
.fs-chat-title {
    font-family: 'Manrope', sans-serif;
    font-size: 16px;
    font-weight: 600;
    color: var(--fs-text);
}
.fs-chat-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--fs-text-faint);
}

.fs-chat-session-list {
    margin-top: 12px;
}
.fs-chat-empty {
    padding: 16px;
    text-align: center;
    color: var(--fs-text-faint);
    font-size: 13px;
    font-family: 'Manrope', sans-serif;
}

/* 结构化数据命中大数字 */
.fs-structured-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 28px;
    font-weight: 700;
    color: var(--fs-success);
    margin: 8px 0 12px 0;
}
.fs-structured-unit {
    font-size: 14px;
    color: var(--fs-text-faint);
    font-weight: 400;
    margin-left: 4px;
}

/* ===== 证据来源标注（参考来源面板 + 节点内联标注） ===== */
.fs-evidence-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 16px;
}
.fs-evidence-card {
    background: var(--fs-bg-card);
    border: 1px solid var(--fs-border);
    border-left: 3px solid var(--fs-accent);
    border-radius: 6px;
    padding: 12px 16px;
    transition: border-color 0.2s ease, background 0.2s ease;
}
.fs-evidence-card:hover {
    border-color: var(--fs-border-bright);
    background: var(--fs-bg-hover);
}
.fs-evidence-head {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 6px;
}
.fs-evidence-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
}
.fs-evidence-badge-annual_report,
.fs-evidence-badge-filing { background: var(--fs-success-bg); color: var(--fs-success); }
.fs-evidence-badge-news { background: var(--fs-info-bg); color: var(--fs-info); }
.fs-evidence-badge-structured_metric { background: rgba(232, 176, 87, 0.12); color: var(--fs-accent); }
.fs-evidence-company {
    font-family: 'Manrope', sans-serif;
    font-size: 13px;
    font-weight: 700;
    color: var(--fs-text);
}
.fs-evidence-code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fs-text-faint);
}
.fs-evidence-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fs-text-dim);
    line-height: 1.7;
    word-break: break-word;
}
.fs-evidence-meta .fs-evidence-sep {
    color: var(--fs-text-faint);
    margin: 0 6px;
}
.fs-evidence-excerpt {
    font-family: 'Noto Serif SC', serif;
    font-size: 12px;
    line-height: 1.7;
    color: var(--fs-text-dim);
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.fs-evidence-link {
    color: var(--fs-info);
    text-decoration: none;
    border-bottom: 1px dotted var(--fs-info);
}
.fs-evidence-link:hover { color: #93c5fd; }

/* 中间节点内的单条证据标注行 */
.fs-evidence-inline {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 3px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
}
.fs-evidence-inline:first-child { border-top: none; }
.fs-evidence-inline-idx {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fs-accent);
    min-width: 18px;
}
.fs-evidence-inline-body {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fs-text-dim);
    line-height: 1.6;
    word-break: break-word;
}
.fs-evidence-inline-body a { color: var(--fs-info); text-decoration: none; }
</style>
"""


def inject_theme() -> None:
    """注入暗色金融终端主题 CSS。"""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
