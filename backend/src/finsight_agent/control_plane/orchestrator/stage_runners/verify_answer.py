from __future__ import annotations

import logging

from finsight_agent.infra.llm import LlmClient
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult

_logger = logging.getLogger(__name__)

_VERIFY_SYSTEM_PROMPT = (
    "You are FinSight Agent V1 answer verifier. "
    "Given the user query, the detected intent, and the final answer, "
    "judge whether the answer actually addresses the query. "
    "Return exactly one JSON object, no markdown: "
    '{"answered": bool, "confidence": "high"|"medium"|"low", '
    '"gaps": [str], "suggested_follow_ups": [str]}. '
    "gaps: what the answer is missing or uncertain. "
    "suggested_follow_ups: concrete next questions the user could ask."
)


def run_verify_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None = None,
    execution_state: dict[str, object],
    llm_client: LlmClient | None = None,
    answer_text: str = "",
) -> StageExecutionResult:
    """synthesize 之后的自检节点：LLM 自评答案是否真正回答了 query。

    产出结构化 verification（answered / confidence / gaps / suggested_follow_ups），
    挂载到 final_response.verification 并进入 trace。
    刻意不做自动重规划循环（避免失控），只暴露"答得怎样"供上层/用户判断。
    LLM 不可用或调用失败时返回中性 verification，不抛出。
    """
    verification: dict = {
        "answered": None,
        "confidence": "unknown",
        "gaps": [],
        "suggested_follow_ups": [],
    }
    if llm_client is not None and answer_text:
        try:
            payload = llm_client.complete_json(
                prompt_name="verify_answer",
                variables={
                    "system_prompt": _VERIFY_SYSTEM_PROMPT,
                    "query": request.query,
                    "intent": router_result.intent,
                    "answer": answer_text,
                },
            )
            verification = {
                "answered": bool(payload.get("answered", False)),
                "confidence": str(payload.get("confidence", "unknown")).strip()
                or "unknown",
                "gaps": [
                    str(g).strip()
                    for g in (payload.get("gaps") or [])
                    if str(g).strip()
                ][:5],
                "suggested_follow_ups": [
                    str(f).strip()
                    for f in (payload.get("suggested_follow_ups") or [])
                    if str(f).strip()
                ][:5],
            }
        except Exception as exc:
            _logger.warning("verify_answer 自检失败，跳过: %s", exc)

    return StageExecutionResult(
        stage_name=StageName.VERIFY_ANSWER.value,
        status="success",
        output_payload={"verification": verification},
        user_summary=(
            f"自检：已回答={verification['answered']}，置信度={verification['confidence']}"
            if answer_text
            else None
        ),
    )
