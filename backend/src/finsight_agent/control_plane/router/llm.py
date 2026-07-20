from __future__ import annotations

import json
import logging
from typing import Any

from finsight_agent.infra.llm import LlmClient
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from .schema import router_result_from_payload

_logger = logging.getLogger(__name__)


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
        _logger.warning(
            "[ROUTER_DEBUG] query=%r payload=%s",
            query,
            json.dumps(payload, ensure_ascii=False)[:1500],
        )
        result = router_result_from_payload(payload)
        _logger.warning(
            "[ROUTER_DEBUG] normalized entities=%s",
            json.dumps(result.entities, ensure_ascii=False)[:1500],
        )
        return result
    except Exception as exc:
        _logger.warning("[ROUTER_DEBUG] route_with_llm 异常被吞掉: %r", exc, exc_info=True)
        return None


def _session_context_payload(
    session_context: SessionContext | None,
) -> dict[str, Any] | None:
    """把 SessionContext 序列化为 router LLM 可消费的 payload。

    v2 增强：
    - 新增 ``active_metrics`` / ``active_time_scope`` 支持指标/时间指代消解
    - 新增 ``recent_turns`` 最近 3 轮原文（短期记忆）
    """
    if session_context is None:
        return None

    # 最近 3 轮原文（用于指代消解与上下文理解）
    recent_turns = [
        {
            "query": turn.query,
            "intent": turn.intent,
            "summary": turn.response_summary,
            "company": turn.entities_snapshot.get("company_name") or "",
            "metric": turn.entities_snapshot.get("metric_raw") or "",
        }
        for turn in session_context.turns[-3:]
    ]

    return {
        "session_id": session_context.session_id,
        "active_topic": session_context.active_topic,
        "active_candidates": session_context.active_candidates,
        "active_metrics": session_context.active_metrics,
        "active_time_scope": session_context.active_time_scope,
        "history_summary": session_context.history_summary,
        "recent_turns": recent_turns,
        "available_follow_ups": session_context.available_follow_ups,
    }
