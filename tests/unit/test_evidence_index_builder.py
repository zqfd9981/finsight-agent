from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from shared.contracts.evidence_detail import (
    SOURCE_TYPE_ANNUAL_REPORT,
    SOURCE_TYPE_NEWS,
    SOURCE_TYPE_STRUCTURED_METRIC,
)
from shared.contracts.stage_observation import StageObservation

from finsight_agent.control_plane.orchestrator.evidence_index_builder import (
    build_evidence_index,
)


def _rag_stage(dataclass_like: bool = True) -> StageObservation:
    """retrieve_evidence 节点：RAG 年报/公告证据。

    dataclass_like=True 走 SimpleNamespace（模拟 EvidenceItem dataclass，
    验证 getattr 路径）；False 走纯 dict（验证 dict 路径）。
    """
    if dataclass_like:
        item = SimpleNamespace(
            evidence_id="ev_rag_001",
            company_code="601012",
            company_name="隆基绿能",
            doc_type="年度报告",
            report_year=2024,
            section_path=["第四节 经营情况", "主营业务"],
            citation=SimpleNamespace(page_start=12, page_end=14),
            excerpt="净利润 540 亿元。",
            support_strength="strong",
        )
        retrieval_result = SimpleNamespace(evidence_items=[item])
        ref = item.evidence_id
    else:
        item = {
            "evidence_id": "ev_rag_002",
            "company_code": "300750",
            "company_name": "宁德时代",
            "doc_type": "年度报告",
            "report_year": 2024,
            "section_path": ["经营情况"],
            "citation": {"page_start": 20, "page_end": 22},
            "excerpt": "营收 3620 亿元。",
            "support_strength": "medium",
        }
        retrieval_result = {"evidence_items": [item]}
        ref = item["evidence_id"]

    return StageObservation(
        stage_name="retrieve_evidence",
        status="success",
        key_outputs={"retrieval_result": retrieval_result},
        evidence_refs=[ref],
    )


def _event_stage() -> StageObservation:
    """collect_event_context 节点：Bocha 事件新闻。"""
    item = {
        "evidence_ref": "bocha:item_001",
        "title": "红海局势升级",
        "source": "bocha",
        "publish_date": "2026-01-15",
        "url": "https://example.com/n1",
        "snippet": "胡塞武装袭击商船。",
    }
    return StageObservation(
        stage_name="collect_event_context",
        status="success",
        key_outputs={"event_context": {"items": [item]}},
        evidence_refs=["bocha:item_001"],
    )


def _structured_stage() -> StageObservation:
    """query_structured_data 节点：年报结构化指标。"""
    sr = {
        "company": "隆基绿能",
        "company_code": "601012",
        "metric": "净利润",
        "value": "540",
        "unit": "亿元",
        "period": "2024-12-31",
        "matched_by": "exact",
    }
    return StageObservation(
        stage_name="query_structured_data",
        status="success",
        key_outputs={"structured_result": sr},
        evidence_refs=[],
    )


def test_build_evidence_index_all_three_sources() -> None:
    orch = SimpleNamespace(
        stage_observations=[
            _rag_stage(dataclass_like=True),
            _rag_stage(dataclass_like=False),
            _event_stage(),
            _structured_stage(),
        ]
    )
    index = build_evidence_index(orch)

    # 三类证据都应入库
    assert "ev_rag_001" in index
    assert "ev_rag_002" in index
    assert "bocha:item_001" in index
    assert any(
        d["source_type"] == SOURCE_TYPE_STRUCTURED_METRIC for d in index.values()
    )

    # 年报 RAG（dataclass 路径）
    rag = index["ev_rag_001"]
    assert rag["source_type"] == SOURCE_TYPE_ANNUAL_REPORT
    assert rag["company_name"] == "隆基绿能"
    assert rag["company_code"] == "601012"
    assert rag["pages"] == "12-14"
    assert rag["section_path"] == ["第四节 经营情况", "主营业务"]
    assert rag["excerpt"] == "净利润 540 亿元。"

    # 年报 RAG（dict 路径）
    rag2 = index["ev_rag_002"]
    assert rag2["company_name"] == "宁德时代"
    assert rag2["pages"] == "20-22"

    # 事件新闻
    news = index["bocha:item_001"]
    assert news["source_type"] == SOURCE_TYPE_NEWS
    assert news["title"] == "红海局势升级"
    assert news["url"] == "https://example.com/n1"
    assert news["publish_date"] == "2026-01-15"

    # 结构化指标
    struct = next(
        d for d in index.values() if d["source_type"] == SOURCE_TYPE_STRUCTURED_METRIC
    )
    assert struct["company_name"] == "隆基绿能"
    assert struct["metric"] == "净利润"
    assert struct["value"] == "540"
    assert struct["unit"] == "亿元"
    assert struct["period"] == "2024-12-31"
    assert struct["evidence_id"].startswith("structured::")


def test_build_evidence_index_empty() -> None:
    assert build_evidence_index(None) == {}
    assert build_evidence_index(SimpleNamespace(stage_observations=[])) == {}


def test_build_evidence_index_skips_missing_ids() -> None:
    # retrieval_result 为 None 时应安全跳过，不报错
    obs = StageObservation(
        stage_name="retrieve_evidence",
        status="success",
        key_outputs={"retrieval_result": None},
        evidence_refs=[],
    )
    assert build_evidence_index(SimpleNamespace(stage_observations=[obs])) == {}
