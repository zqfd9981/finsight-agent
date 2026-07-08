from __future__ import annotations

from finsight_agent.infra.llm import LlmClient
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult

from .schema import plan_from_payload


def build_plan_with_llm(
    llm_client: LlmClient,
    system_prompt: str,
    router_result: RouterResult,
    *,
    strategy_payload: dict[str, str] | None = None,
) -> Plan | None:
    try:
        payload = llm_client.complete_json(
            prompt_name="planner",
            variables={
                "router_result": {
                    "intent": router_result.intent,
                    "follow_up_type": router_result.follow_up_type,
                    "confidence": router_result.confidence,
                    "entities": router_result.entities,
                    "needs": router_result.needs,
                    "constraints": router_result.constraints,
                },
                "strategy_payload": strategy_payload or {},
                "system_prompt": system_prompt,
            },
        )
        return plan_from_payload(payload)
    except Exception:
        return None
