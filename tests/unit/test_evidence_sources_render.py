from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.pages.analysis_view import (  # noqa: E402
    _evidence_badge,
    _evidence_meta_line,
    _render_evidence_card,
    _render_evidence_inline,
)

_RAG_DETAIL = {
    "evidence_id": "ev_001",
    "source_type": "annual_report",
    "company_name": "隆基绿能",
    "company_code": "601012",
    "doc_type": "年度报告",
    "report_year": "2024",
    "section_path": ["第四节 经营情况", "主营业务"],
    "pages": "12-14",
    "excerpt": "净利润 540 亿元。",
    "support_strength": "strong",
    "url": "",
    "title": "",
    "publish_date": "",
    "source": "retrieval",
    "metric": "",
    "value": "",
    "unit": "",
    "period": "",
    "matched_by": "",
}

_NEWS_DETAIL = {
    "evidence_id": "bocha:item_001",
    "source_type": "news",
    "company_name": "",
    "company_code": "",
    "doc_type": "事件新闻",
    "report_year": "",
    "section_path": [],
    "pages": "",
    "excerpt": "胡塞武装袭击商船。",
    "support_strength": "",
    "url": "https://example.com/n1",
    "title": "红海局势升级",
    "publish_date": "2026-01-15",
    "source": "bocha",
    "metric": "",
    "value": "",
    "unit": "",
    "period": "",
    "matched_by": "",
}

_STRUCT_DETAIL = {
    "evidence_id": "structured::隆基绿能::净利润::2024-12-31",
    "source_type": "structured_metric",
    "company_name": "隆基绿能",
    "company_code": "601012",
    "doc_type": "年报结构化数据",
    "report_year": "2024",
    "section_path": [],
    "pages": "",
    "excerpt": "净利润: 540 亿元",
    "support_strength": "",
    "url": "",
    "title": "",
    "publish_date": "",
    "source": "structured_data",
    "metric": "净利润",
    "value": "540",
    "unit": "亿元",
    "period": "2024-12-31",
    "matched_by": "exact",
}


def test_badge_renders_label_and_class() -> None:
    html = _evidence_badge("annual_report")
    assert "fs-evidence-badge-annual_report" in html
    assert "年报 / 公告" in html


def test_meta_line_annual_report() -> None:
    meta = _evidence_meta_line(_RAG_DETAIL)
    assert "年度报告" in meta
    assert "2024" in meta
    assert "第四节 经营情况 / 主营业务" in meta
    assert "p12-14" in meta


def test_meta_line_news() -> None:
    meta = _evidence_meta_line(_NEWS_DETAIL)
    assert "bocha" in meta
    assert "2026-01-15" in meta


def test_card_annual_report_contains_company_and_excerpt() -> None:
    card = _render_evidence_card(_RAG_DETAIL)
    assert "隆基绿能" in card
    assert "601012" in card
    assert "净利润 540 亿元。" in card
    assert "fs-evidence-card" in card


def test_card_news_contains_link() -> None:
    card = _render_evidence_card(_NEWS_DETAIL)
    assert "红海局势升级" in card
    assert 'href="https://example.com/n1"' in card
    assert "原文↗" in card


def test_inline_structured_metric() -> None:
    inline = _render_evidence_inline(1, _STRUCT_DETAIL)
    assert "隆基绿能" in inline
    assert "净利润" in inline
    assert "540 亿元" in inline
    assert "2024-12-31" in inline
    assert "fs-evidence-inline" in inline


def _has_blank_line(s: str) -> bool:
    return any(line.strip() == "" for line in s.splitlines())


def test_card_has_no_blank_lines() -> None:
    """根因回归：每张卡片不得含空白行，否则 CommonMark <div> HTML 块会在空行处截断，
    导致面板以原始 html 文本显示。"""
    for detail in (_RAG_DETAIL, _NEWS_DETAIL, _STRUCT_DETAIL):
        card = _render_evidence_card(detail)
        assert not _has_blank_line(card), f"card 含空白行: {detail['evidence_id']}"


def test_panel_has_no_blank_lines(monkeypatch) -> None:
    """整块面板（多卡片拼接）不得含空白行。"""
    import re

    from frontend.streamlit_app.pages import analysis_view

    captured: list[str] = []

    def fake_markdown(body, *a, **k):
        captured.append(body)

    monkeypatch.setattr(analysis_view.st, "markdown", fake_markdown)

    idx = {
        _RAG_DETAIL["evidence_id"]: _RAG_DETAIL,
        _NEWS_DETAIL["evidence_id"]: _NEWS_DETAIL,
        _STRUCT_DETAIL["evidence_id"]: _STRUCT_DETAIL,
    }
    analysis_view._render_evidence_sources(idx)

    panel_html = "".join(captured)
    # 防御性压缩后也应无空白行
    panel_html = re.sub(r"\n[ \t]*\n", "\n", panel_html)
    assert not _has_blank_line(panel_html), "面板 HTML 含空白行，会被截断为原始文本"
