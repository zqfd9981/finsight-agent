from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.contracts.stage_observation import StageObservation
from shared.contracts.trace_block import TraceBlock


@dataclass(slots=True)
class StageExecutionResult:
    """orchestrator 内部使用的阶段执行结果。"""

    stage_name: str
    status: str
    output_payload: dict[str, Any] = field(default_factory=dict)
    confidence_signals: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    degraded_reason: str | None = None
    user_summary: str | None = None


@dataclass(slots=True)
class OrchestrationResult:
    """orchestrator 内部汇总结果。"""

    session_id: str
    stage_observations: list[StageObservation] = field(default_factory=list)
    trace_blocks: list[TraceBlock] = field(default_factory=list)
