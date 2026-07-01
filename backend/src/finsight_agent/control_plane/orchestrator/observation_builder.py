from __future__ import annotations

from shared.contracts.stage_observation import StageObservation

from .models import StageExecutionResult


def build_stage_observation(
    *,
    stage_result: StageExecutionResult,
    observation_id: str,
    input_summary: dict[str, object] | None = None,
) -> StageObservation:
    """把内部阶段结果映射成共享 observation contract。"""

    return StageObservation(
        observation_id=observation_id,
        stage_name=stage_result.stage_name,
        status=stage_result.status,
        input_summary=dict(input_summary or {}),
        key_outputs=dict(stage_result.output_payload),
        confidence_signals=dict(stage_result.confidence_signals),
        evidence_refs=list(stage_result.evidence_refs),
        notes=stage_result.user_summary,
    )
