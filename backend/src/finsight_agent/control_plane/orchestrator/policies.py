from __future__ import annotations

from shared.contracts.guardrail_or_error_response import GuardrailOrErrorResponse
from shared.enums.intent import Intent
from shared.enums.response_type import ResponseType


def should_short_circuit(router_intent: str) -> bool:
    return router_intent == Intent.OUT_OF_SCOPE.value


def build_guardrail_response(
    reason_code: str,
    progress_state: str,
    partial_answer: str,
) -> GuardrailOrErrorResponse:
    return GuardrailOrErrorResponse(
        response_type=ResponseType.GUARDRAIL.value,
        reason_code=reason_code,
        progress_state=progress_state,
        partial_answer=partial_answer,
        suggested_next_actions=["请改问结构化指标、事件影响或证据查找类问题。"],
        trace_refs=[],
    )
