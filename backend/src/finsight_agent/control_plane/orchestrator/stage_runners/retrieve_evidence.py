from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from finsight_agent.capabilities.retrieval.retrieval_agent import RetrievalAgent
from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from finsight_agent.infra.llm.client import LlmClient
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult

_logger = logging.getLogger(__name__)


def run_retrieve_evidence_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    retrieval_facade: RetrievalFacade,
    llm_client: LlmClient | None = None,
) -> StageExecutionResult:
    constraints = stage_constraints or {}
    limit = int(constraints.get("retrieval_budget") or 5)
    retrieval_query = _build_retrieval_query(
        request=request,
        router_result=router_result,
        stage_constraints=constraints,
        execution_state=execution_state,
    )
    context_summary = _build_context_summary(execution_state)

    # RetrievalAgent 内部 trace，用于调试和可观测性
    agent_rounds_trace: list[dict] = []
    agent_rewritten_queries: list[str] = []
    agent_reflect_reason: str = ""
    agent_used = False

    if llm_client is not None:
        try:
            agent = RetrievalAgent(
                llm_client=llm_client,
                retrieval_facade=retrieval_facade,
            )
            agent_state = agent.retrieve(
                original_query=retrieval_query,
                intent=router_result.intent,
                entities=dict(router_result.entities or {}),
                context_summary=context_summary,
                retrieval_limit=limit,
            )
            retrieval_result = agent_state.get("retrieval_result")
            if retrieval_result is None:
                retrieval_result = retrieval_facade.retrieve_evidence(
                    raw_query=retrieval_query,
                    limit=limit,
                )
            agent_rounds_trace = list(agent_state.get("rounds_trace", []))
            agent_rewritten_queries = list(agent_state.get("all_rewritten_queries", []))
            agent_reflect_reason = str(agent_state.get("reflect_reason") or "")
            agent_used = True
            _logger.info(
                "retrieval agent finished: rounds=%d, queries=%d, evidence=%d",
                len(agent_rounds_trace),
                len(agent_rewritten_queries),
                len(retrieval_result.evidence_items),
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("retrieval agent failed: %s; fallback to direct retrieve", exc)
            retrieval_result = retrieval_facade.retrieve_evidence(
                raw_query=retrieval_query,
                limit=limit,
            )
    else:
        retrieval_result = retrieval_facade.retrieve_evidence(
            raw_query=retrieval_query,
            limit=limit,
        )

    evidence_refs = [
        item.evidence_id
        for item in retrieval_result.evidence_items
        if item.evidence_id
    ]
    summary = f"已检索到 {len(evidence_refs)} 条证据。"

    # output_payload 包含 retrieval_result（供下游 synthesize_answer 消费）
    # 和 agent trace（供 trace_blocks 暴露给前端调试）
    output_payload: dict[str, Any] = {"retrieval_result": retrieval_result}
    if agent_used:
        output_payload["agent_trace"] = {
            "rounds_count": len(agent_rounds_trace),
            "rounds_trace": agent_rounds_trace,
            "rewritten_queries": agent_rewritten_queries,
            "reflect_reason": agent_reflect_reason,
        }

    return StageExecutionResult(
        stage_name=StageName.RETRIEVE_EVIDENCE.value,
        status="success",
        output_payload=output_payload,
        evidence_refs=evidence_refs,
        user_summary=summary,
    )


def _build_retrieval_query(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object],
    execution_state: dict[str, object],
) -> str:
    entities = router_result.entities
    collect_event_context = _read_stage_output(
        execution_state.get("collect_event_context")
    )
    analyze_targets = _read_stage_output(execution_state.get("analyze_targets"))
    event_context = _read_mapping(collect_event_context.get("event_context"))
    event_entities = _read_mapping(collect_event_context.get("event_entities"))
    prioritized_target = str(stage_constraints.get("target") or "").strip()
    fallback_target = str(entities.get("target") or "").strip()

    query_parts = [
        request.query.strip(),
        str(entities.get("claim") or "").strip(),
        prioritized_target,
        str(event_context.get("event") or event_entities.get("event") or entities.get("event") or "").strip(),
        *_normalize_parts(
            event_context.get("themes")
            or event_entities.get("themes")
            or entities.get("themes")
        ),
        str(
            event_context.get("time_scope")
            or event_entities.get("time_scope")
            or entities.get("time_scope_raw")  # 新格式扁平字段（schema.py 已展开）
            or entities.get("period_end")  # 新格式日期 fallback
            or _safe_str(entities.get("time_scope"))  # 旧格式字符串（dict 时返回空）
            or ""
        ).strip(),
        fallback_target,
        *_normalize_parts(analyze_targets.get("target_scope") or stage_constraints.get("target_scope")),
    ]

    normalized_parts: list[str] = []
    seen: set[str] = set()
    for part in query_parts:
        if not part:
            continue
        if part in seen:
            continue
        normalized_parts.append(part)
        seen.add(part)

    return " ".join(normalized_parts)


def _build_context_summary(execution_state: dict[str, object]) -> str:
    """从上游 stage 输出中提炼上下文摘要，供 RetrievalAgent 的改写节点使用。"""
    collect_event_context = _read_stage_output(
        execution_state.get("collect_event_context")
    )
    analyze_targets = _read_stage_output(execution_state.get("analyze_targets"))
    event_context = _read_mapping(collect_event_context.get("event_context"))
    event_entities = _read_mapping(collect_event_context.get("event_entities"))

    parts: list[str] = []
    event_name = str(event_context.get("event") or event_entities.get("event") or "").strip()
    if event_name:
        parts.append(f"事件: {event_name}")
    themes = _normalize_parts(
        event_context.get("themes") or event_entities.get("themes")
    )
    if themes:
        parts.append(f"主题: {', '.join(themes)}")
    target_scope = _normalize_parts(analyze_targets.get("target_scope"))
    if target_scope:
        parts.append(f"目标范围: {', '.join(target_scope)}")
    time_scope = str(
        event_context.get("time_scope") or event_entities.get("time_scope") or ""
    ).strip()
    if time_scope:
        parts.append(f"时间范围: {time_scope}")
    return "; ".join(parts)


def _read_stage_output(stage_value: object) -> dict[str, object]:
    if isinstance(stage_value, StageExecutionResult):
        return _read_mapping(stage_value.output_payload)
    return _read_mapping(stage_value)


def _read_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_parts(value: object) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, Iterable):
        normalized: list[str] = []
        for item in value:
            candidate = str(item).strip()
            if candidate:
                normalized.append(candidate)
        return normalized
    return []


def _safe_str(value: object) -> str:
    """把值安全转成字符串；dict 返回空字符串（避免 str(dict) 产生垃圾）。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        return ""
    return str(value).strip()
