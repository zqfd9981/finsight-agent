"""对话视图（chat_view）证据来源标注回归测试。

验证 chat_view 在「对话视图」下也能渲染：
1. 回答下方的「参考来源 · 来源标注」面板；
2. 中间执行节点基于 evidence_index 的逐条证据标注。

不涉及真实后端/torch——用最小桩数据驱动渲染函数，
mock 掉 streamlit.markdown 以捕获 HTML 输出。
"""

from __future__ import annotations

import sys
import types

# 让 streamlit 在非运行时可被 import（仅取 markdown 等符号）
import streamlit as st

_CAPTURED: list[str] = []


def _fake_markdown(body: str, *args, **kwargs) -> None:
    _CAPTURED.append(body)


st.markdown = _fake_markdown  # type: ignore[assignment]

REPO_ROOT = "."
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, f"{REPO_ROOT}/frontend")
sys.path.insert(0, f"{REPO_ROOT}/shared")
sys.path.insert(0, f"{REPO_ROOT}/backend/src")

import frontend.streamlit_app.pages.chat_view as chat_view  # noqa: E402


def _make_trace_block(stage_name: str, evidence_refs: list[str]) -> object:
    return types.SimpleNamespace(
        block_type="execution",
        payload_summary={
            "stage_observations": [
                {
                    "stage_name": stage_name,
                    "status": "success",
                    "key_outputs": {"evidence_ref_count": len(evidence_refs)},
                    "message": "",
                    "evidence_refs": evidence_refs,
                }
            ]
        },
    )


def _sample_evidence_index() -> dict:
    return {
        "evidence_0001": {
            "evidence_id": "evidence_0001",
            "source_type": "annual_report",
            "company_name": "隆基绿能",
            "company_code": "601012",
            "doc_type": "年度报告",
            "report_year": "2024",
            "section_path": ["管理层讨论与分析"],
            "pages": "12-14",
            "excerpt": "公司实现营业总收入 ...",
            "support_strength": "",
            "url": "",
            "title": "",
            "publish_date": "",
            "source": "",
            "metric": "",
            "value": "",
            "unit": "",
            "period": "",
            "matched_by": "",
        },
        "bocha:item_005": {
            "evidence_id": "bocha:item_005",
            "source_type": "news",
            "company_name": "",
            "company_code": "",
            "doc_type": "事件新闻",
            "report_year": "",
            "section_path": [],
            "pages": "",
            "excerpt": "隆基绿能预计2026年半年度净亏损 ...",
            "support_strength": "",
            "url": "https://example.com/news/005",
            "title": "隆基绿能:预计2026年半年度净亏损34亿元-38亿元",
            "publish_date": "2026-07-14T00:00:00+08:00",
            "source": "bocha",
            "metric": "",
            "value": "",
            "unit": "",
            "period": "",
            "matched_by": "",
        },
    }


def test_chat_view_bottom_panel_renders() -> None:
    """对话视图回答下方应渲染参考来源面板。"""
    _CAPTURED.clear()
    idx = _sample_evidence_index()
    chat_view._render_evidence_sources(idx)
    merged = "\n".join(_CAPTURED)
    assert "参考来源 · 来源标注" in merged, "缺少参考来源面板标题"
    assert "fs-evidence-panel" in merged, "缺少面板容器"
    assert "隆基绿能" in merged, "年报证据公司名未渲染"
    assert "原文" in merged, "新闻原文链接未渲染"


def test_chat_view_midnode_annotation_renders() -> None:
    """对话视图中间节点应基于 evidence_index 渲染逐条证据标注。"""
    _CAPTURED.clear()
    idx = _sample_evidence_index()
    trace_blocks = [
        _make_trace_block(
            "retrieve_evidence", ["evidence_0001", "bocha:item_005"]
        )
    ]
    chat_view._render_trace_blocks(trace_blocks, evidence_index=idx)
    merged = "\n".join(_CAPTURED)
    assert "fs-evidence-inline" in merged, "中间节点缺少证据逐条标注"
    assert "隆基绿能" in merged, "中间节点未解析出年报证据来源"


def test_chat_view_empty_evidence_no_panel() -> None:
    """evidence_index 为空时不应渲染面板（避免空标题）。"""
    _CAPTURED.clear()
    chat_view._render_evidence_sources({})
    merged = "\n".join(_CAPTURED)
    assert "参考来源 · 来源标注" not in merged, "空证据不应渲染面板"
    assert "fs-evidence-panel" not in merged
