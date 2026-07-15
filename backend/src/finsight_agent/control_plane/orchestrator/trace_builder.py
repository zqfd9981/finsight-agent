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
        agent_trace = key_outputs.get("agent_trace") or {}
        result: dict[str, object] = {
            "evidence_ref_count": len(observation.evidence_refs),
        }
        if agent_trace:
            result["agent_rounds_count"] = int(agent_trace.get("rounds_count") or 0)
            result["agent_rewritten_queries"] = list(agent_trace.get("rewritten_queries") or [])
            result["agent_reflect_reason"] = str(agent_trace.get("reflect_reason") or "")
            # rounds_trace 可能含 dict，截断避免 trace 过大
            rounds_trace = agent_trace.get("rounds_trace") or []
            result["agent_rounds_trace"] = list(rounds_trace[:3])
        return result
    if stage_name == "synthesize_answer":
        final_response = key_outputs.get("final_response")
        return {
            "response_type": str(getattr(final_response, "response_type", "") or "").strip(),
        }
    if stage_name == "query_structured_data":
        # 暴露结构化数据查询结果到 trace，便于前端展示命中/未命中状态
        structured_result = key_outputs.get("structured_result") or {}
        if isinstance(structured_result, dict):
            return {
                "company": str(structured_result.get("company") or structured_result.get("company_name") or ""),
                "metric": str(structured_result.get("metric") or structured_result.get("metric_name") or ""),
                "value": str(structured_result.get("value") or ""),
                "unit": str(structured_result.get("unit") or ""),
                "time_scope": str(structured_result.get("time_scope") or ""),
                "is_degraded": bool(structured_result.get("is_degraded", True)),
                "matched_by": str(structured_result.get("matched_by") or ""),
                "source_summary": str(structured_result.get("source_summary") or "")[:200],
                "confidence": str(structured_result.get("confidence") or ""),
            }
        return {}
    return {}
