from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dataclasses import asdict  # noqa: E402

from shared.contracts.analysis_response_envelope import (  # noqa: E402
    AnalysisResponseEnvelope,
)
from shared.contracts.final_response import FinalResponse  # noqa: E402
from shared.contracts.stage_observation import StageObservation  # noqa: E402
from shared.contracts.trace_block import TraceBlock  # noqa: E402
from finsight_agent.capabilities.retrieval.models import (  # noqa: E402
    CitationRecord,
    EvidenceItem,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from finsight_agent.control_plane.orchestrator.evidence_index_builder import (  # noqa: E402
    build_evidence_index,
)
from frontend.streamlit_app.api_client import (  # noqa: E402
    WorkbenchApiClient,
)


def _orch_with_rag() -> SimpleNamespace:
    item = EvidenceItem(
        evidence_id="ev_x",
        rank=1,
        support_strength="strong",
        matched_chunk_id="c",
        matched_parent_id="p",
        excerpt="净利润 540 亿元。",
        parent_context="",
        citation=CitationRecord(document_id="d", page_start=12, page_end=14, page_anchor=12),
        retrieval_scores=RetrievalScoreBreakdown(),
        company_code="601012",
        company_name="隆基绿能",
        doc_type="年度报告",
        section_path=["经营情况"],
        report_year="2024",
    )
    rr = RetrievalResult(request_id="r", normalized_claim="x", evidence_items=[item])
    obs = StageObservation(
        stage_name="retrieve_evidence",
        status="success",
        key_outputs={"retrieval_result": rr},
        evidence_refs=["ev_x"],
    )
    return SimpleNamespace(stage_observations=[obs])


def test_evidence_index_survives_full_contract_roundtrip() -> None:
    orch = _orch_with_rag()
    index = build_evidence_index(orch)
    assert "ev_x" in index

    envelope = AnalysisResponseEnvelope(
        session_id="s1",
        response=FinalResponse(answer_markdown="测试回答"),
        trace_blocks=[
            TraceBlock(
                block_type="execution",
                title="执行结果",
                status="success",
                payload_summary={},
                raw_refs=[],
            )
        ],
        evidence_index=index,
    )

    # 1) 后端 asdict 序列化（与生产一致）
    payload = asdict(envelope)
    assert "evidence_index" in payload
    assert payload["evidence_index"]["ev_x"]["company_name"] == "隆基绿能"

    # 2) 模拟 HTTP JSON 往返
    wire = json.loads(json.dumps(payload, default=str))
    assert wire["evidence_index"]["ev_x"]["pages"] == "12-14"

    # 3) 前端 parse_response —— 这是之前会「静默丢弃」evidence_index 的关键点
    client = WorkbenchApiClient()
    parsed = client.parse_response(wire)
    assert parsed.evidence_index, "前端 parse_response 丢弃了 evidence_index！"
    assert parsed.evidence_index["ev_x"]["company_name"] == "隆基绿能"
    assert parsed.evidence_index["ev_x"]["source_type"] == "annual_report"
