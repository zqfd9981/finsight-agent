"""实证：build_evidence_index 在真实 dataclass 接缝下能否从 execute_graph 产出的
OrchestrationResult 中提取证据。

重点验证：旧测试用 SimpleNamespace 模拟，本测试用真实的
RetrievalResult / EvidenceItem / StageObservation / StageExecutionResult，
精确复刻 run_retrieve_evidence_stage 等 runner 的 output_payload 形状。
"""
from __future__ import annotations

import sys
from pathlib import Path

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

from finsight_agent.capabilities.retrieval.models import (
    CitationRecord,
    EvidenceItem,
    RetrievalResult,
)
from finsight_agent.control_plane.orchestrator.evidence_index_builder import (
    build_evidence_index,
)
from finsight_agent.control_plane.orchestrator.models import (
    OrchestrationResult,
    StageExecutionResult,
)


def _rag_stage() -> StageObservation:
    ev = EvidenceItem(
        evidence_id="ev_real_001",
        rank=1,
        support_strength="strong",
        matched_chunk_id="c1",
        matched_parent_id="p1",
        excerpt="隆基绿能 2024 年净利润为 -36 亿元。",
        parent_context="",
        citation=CitationRecord(document_id="d1", page_start=12, page_end=14, page_anchor=13),
        retrieval_scores=None,
        company_code="601012",
        company_name="隆基绿能",
        doc_type="年度报告",
        section_path=["第四节 经营情况", "主营业务"],
        report_year="2024",
    )
    rr = RetrievalResult(
        request_id="r1",
        normalized_claim="红海 隆基绿能",
        evidence_items=[ev],
    )
    # 复刻 run_retrieve_evidence_stage 的 output_payload 形状
    stage_result = StageExecutionResult(
        stage_name="retrieve_evidence",
        status="success",
        output_payload={"retrieval_result": rr},
        evidence_refs=[ev.evidence_id],
    )
    return StageObservation(
        observation_id="obs1",
        stage_name=stage_result.stage_name,
        status=stage_result.status,
        key_outputs=dict(stage_result.output_payload),
        evidence_refs=list(stage_result.evidence_refs),
    )


def _event_stage() -> StageObservation:
    item = {
        "evidence_ref": "bocha:item_001",
        "title": "红海局势升级影响航运",
        "source": "bocha",
        "publish_date": "2026-01-15",
        "url": "https://example.com/n1",
        "snippet": "胡塞武装袭击商船。",
    }
    event_context = {"event": "红海", "themes": ["航运"], "items": [item]}
    stage_result = StageExecutionResult(
        stage_name="collect_event_context",
        status="success",
        output_payload={"event_context": event_context},
        evidence_refs=["bocha:item_001"],
    )
    return StageObservation(
        observation_id="obs2",
        stage_name=stage_result.stage_name,
        status=stage_result.status,
        key_outputs=dict(stage_result.output_payload),
        evidence_refs=list(stage_result.evidence_refs),
    )


def _structured_stage() -> StageObservation:
    sr = {
        "company": "隆基绿能",
        "company_code": "601012",
        "metric": "净利润",
        "value": "540",
        "unit": "亿元",
        "period": "2024-12-31",
        "matched_by": "exact",
    }
    stage_result = StageExecutionResult(
        stage_name="query_structured_data",
        status="success",
        output_payload={"structured_result": sr},
        evidence_refs=[],
    )
    return StageObservation(
        observation_id="obs3",
        stage_name=stage_result.stage_name,
        status=stage_result.status,
        key_outputs=dict(stage_result.output_payload),
        evidence_refs=list(stage_result.evidence_refs),
    )


def test_real_dataclass_seam() -> None:
    orch = OrchestrationResult(
        session_id="sess_test",
        stage_observations=[_rag_stage(), _event_stage(), _structured_stage()],
    )
    index = build_evidence_index(orch)

    # 三类证据都应被提取
    assert "ev_real_001" in index, f"RAG 证据缺失，index keys={list(index.keys())}"
    assert "bocha:item_001" in index, f"新闻证据缺失，index keys={list(index.keys())}"
    struct = [d for d in index.values() if d["source_type"] == SOURCE_TYPE_STRUCTURED_METRIC]
    assert struct, f"结构化指标缺失，index={index}"

    rag = index["ev_real_001"]
    assert rag["source_type"] == SOURCE_TYPE_ANNUAL_REPORT
    assert rag["company_name"] == "隆基绿能"
    assert rag["pages"] == "12-14", f"pages 解析错误: {rag['pages']!r}"
    assert rag["report_year"] == "2024"

    news = index["bocha:item_001"]
    assert news["source_type"] == SOURCE_TYPE_NEWS
    assert news["url"] == "https://example.com/n1"


if __name__ == "__main__":
    test_real_dataclass_seam()
    print("PASS: real-dataclass seam test")
