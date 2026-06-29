from __future__ import annotations

from typing import Any

from finsight_agent.infra.llm import LlmClient
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from .schema import router_result_from_payload


def route_with_llm(
    llm_client: LlmClient,
    system_prompt: str,
    query: str,
    session_context: SessionContext | None,
) -> RouterResult | None:
    try:
        payload = llm_client.complete_json(
            prompt_name="router",
            variables={
                "query": query,
                "session_context": _session_context_payload(session_context),
                "system_prompt": system_prompt,
            },
        )
        return router_result_from_payload(payload)
    except Exception:
        return None


def _session_context_payload(
    session_context: SessionContext | None,
) -> dict[str, Any] | None:
    if session_context is None:
        return None
    return {
        "session_id": session_context.session_id,
        "active_topic": session_context.active_topic,
        "active_candidates": session_context.active_candidates,
        "history_summary": session_context.history_summary,
        "available_follow_ups": session_context.available_follow_ups,
    }
