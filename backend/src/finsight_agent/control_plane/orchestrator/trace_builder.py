from __future__ import annotations

from shared.contracts.trace_block import TraceBlock
from shared.enums.response_type import ResponseType

from .models import OrchestrationResult


def build_execution_trace_block(result: OrchestrationResult) -> TraceBlock:
    completed_stages = [
        observation.stage_name
        for observation in result.stage_observations
    ]
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
        },
        raw_refs=completed_stages,
    )
