from __future__ import annotations

from shared.contracts.trace_block import TraceBlock
from shared.enums.response_type import ResponseType
from shared.contracts.stage_observation import StageObservation

from .models import OrchestrationResult


def build_execution_trace_block(result: OrchestrationResult) -> TraceBlock:
    completed_stages = [
        observation.stage_name
        for observation in result.stage_observations
    ]
    stage_statuses = {
        observation.stage_name: observation.status
        for observation in result.stage_observations
    }
    status = (
        ResponseType.SUCCESS.value
        if result.final_response is not None
        else ResponseType.DEGRADED.value
    )
    return TraceBlock(
        block_type="execution",
        title="执行结果",
        status=status,
        payload_summary={
            "completed_stages": completed_stages,
            "observation_count": len(result.stage_observations),
            "has_final_response": result.final_response is not None,
            "has_guardrail_response": result.guardrail_response is not None,
            "stage_statuses": stage_statuses,
            "stage_observations": [
                _summarize_stage_observation(observation)
                for observation in result.stage_observations
            ],
        },
        raw_refs=completed_stages,
    )


def _summarize_stage_observation(observation: StageObservation) -> dict[str, object]:
    return {
        "stage_name": observation.stage_name,
        "status": observation.status,
        "key_outputs": _summarize_key_outputs(observation),
        "evidence_refs": list(observation.evidence_refs),
    }


def _summarize_key_outputs(observation: StageObservation) -> dict[str, object]:
    key_outputs = observation.key_outputs
    stage_name = observation.stage_name

    if stage_name == "collect_event_context":
        return {
            "strategy": str(key_outputs.get("strategy") or "").strip(),
            "source_status": dict(key_outputs.get("source_status") or {}),
        }
    if stage_name == "analyze_targets":
        return {
            "target_scope": list(key_outputs.get("target_scope") or []),
            "analysis_mode": str(key_outputs.get("analysis_mode") or "").strip(),
            "confidence": str(key_outputs.get("confidence") or "").strip(),
        }
    if stage_name == "retrieve_evidence":
        return {
            "evidence_ref_count": len(observation.evidence_refs),
        }
    if stage_name == "synthesize_report":
        final_response = key_outputs.get("final_response")
        return {
            "response_type": str(getattr(final_response, "response_type", "") or "").strip(),
        }
    return {}
