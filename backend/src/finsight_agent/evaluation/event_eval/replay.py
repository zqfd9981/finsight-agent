from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope

from .checks import run_event_eval_checks
from .fixture_loader import load_event_eval_cases
from .models import CheckResult, EventEvalCase, ReplayResult


@dataclass(slots=True)
class ReplayRunRecord:
    """描述单条样本回放后的完整记录。"""

    case: EventEvalCase
    result: ReplayResult
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "case": self.case.to_dict(),
            "result": self.result.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
        }


def replay_event_cases(
    fixture_path: Path,
    *,
    case_ids: list[str] | None = None,
    service: WorkbenchBackendApiService | None = None,
    include_trace: bool = True,
) -> list[ReplayRunRecord]:
    """批量回放事件评测样本。"""

    workbench_service = service or WorkbenchBackendApiService()
    records: list[ReplayRunRecord] = []
    selected_case_ids = {item for item in (case_ids or []) if item}
    for case in load_event_eval_cases(fixture_path):
        if selected_case_ids and case.case_id not in selected_case_ids:
            continue
        envelope = workbench_service.build_response(
            AnalysisRequest(query=case.query, include_trace=include_trace)
        )
        result = build_replay_result(case, envelope)
        checks = run_event_eval_checks(case, result)
        records.append(ReplayRunRecord(case=case, result=result, checks=checks))
    return records


def build_replay_result(
    case: EventEvalCase,
    envelope: AnalysisResponseEnvelope,
) -> ReplayResult:
    """从统一响应包裹对象中提取评测所需字段。"""

    actual_intent = ""
    actual_strategy = ""
    target_keywords: list[str] = []
    evidence_ref_count = 0

    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            actual_intent = str(block.payload_summary.get("intent") or "")
        if block.block_type != "execution":
            continue

        observations = block.payload_summary.get("stage_observations") or []
        for observation in observations:
            if observation.get("stage_name") == "collect_event_context":
                key_outputs = observation.get("key_outputs") or {}
                actual_strategy = str(key_outputs.get("strategy") or actual_strategy)
                evidence_ref_count += len(observation.get("evidence_refs") or [])
            if observation.get("stage_name") == "analyze_targets":
                key_outputs = observation.get("key_outputs") or {}
                target_keywords.extend(
                    [
                        str(item).strip()
                        for item in (key_outputs.get("target_scope") or [])
                        if str(item).strip()
                    ]
                )
                evidence_ref_count += len(observation.get("evidence_refs") or [])

    response = envelope.response
    summary = getattr(response, "summary", "") or ""
    response_type = getattr(response, "response_type", "degraded") or "degraded"
    degraded = response_type != "success"

    return ReplayResult(
        case_id=case.case_id,
        query=case.query,
        actual_intent=actual_intent,
        actual_strategy=actual_strategy,
        response_type=response_type,
        degraded=degraded,
        target_count=len(target_keywords),
        evidence_ref_count=evidence_ref_count,
        summary=summary,
        failure_reason=None if summary else "empty_summary",
        target_keywords=target_keywords,
    )
