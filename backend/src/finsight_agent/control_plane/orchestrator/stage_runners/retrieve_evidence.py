from __future__ import annotations

from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_retrieve_evidence_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    retrieval_facade: RetrievalFacade,
) -> StageExecutionResult:
    constraints = stage_constraints or {}
    limit = int(constraints.get("retrieval_budget") or 5)
    retrieval_result = retrieval_facade.retrieve_evidence(
        raw_query=request.query,
        limit=limit,
    )
    evidence_refs = [
        item.evidence_id
        for item in retrieval_result.evidence_items
        if item.evidence_id
    ]
    summary = f"已检索到 {len(evidence_refs)} 条证据。"

    return StageExecutionResult(
        stage_name=StageName.RETRIEVE_EVIDENCE.value,
        status="success",
        output_payload={"retrieval_result": retrieval_result},
        evidence_refs=evidence_refs,
        user_summary=summary,
    )
