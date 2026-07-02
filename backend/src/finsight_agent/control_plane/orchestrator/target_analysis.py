from __future__ import annotations

from typing import Any

from finsight_agent.infra.llm import LlmClient


class TargetAnalysisService:
    """受约束的目标分析服务。

    这里不让 LLM 自由输出散文，而是要求产出固定结构，便于 orchestrator
    在后续阶段消费，也便于测试和降级。
    """

    def __init__(self, *, llm_client: LlmClient | None = None) -> None:
        self._llm_client = llm_client or LlmClient()

    def analyze_targets(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        candidate_pool: list[str],
    ) -> dict[str, Any]:
        payload = self._llm_client.complete_json(
            prompt_name="event_target_analysis",
            variables={
                "query": query,
                "event_context": event_context,
                "candidate_pool": candidate_pool,
            },
        )
        return self._validate_payload(payload)

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_scope = payload.get("target_scope")
        ranked_targets = payload.get("ranked_targets")
        if not isinstance(target_scope, list):
            raise ValueError("target_scope must be a list")
        if not isinstance(ranked_targets, list):
            raise ValueError("ranked_targets must be a list")

        normalized_scope = _normalize_string_list(target_scope)
        normalized_ranked_targets: list[dict[str, str]] = []
        for item in ranked_targets:
            if not isinstance(item, dict):
                raise ValueError("ranked_targets items must be objects")
            normalized_item = {
                "target": _require_text(item.get("target"), "ranked_targets.target"),
                "target_type": _require_text(
                    item.get("target_type"),
                    "ranked_targets.target_type",
                ),
                "impact_direction": _require_text(
                    item.get("impact_direction"),
                    "ranked_targets.impact_direction",
                ),
                "reasoning_summary": _require_text(
                    item.get("reasoning_summary"),
                    "ranked_targets.reasoning_summary",
                ),
                "confidence": _require_text(
                    item.get("confidence"),
                    "ranked_targets.confidence",
                ),
            }
            normalized_ranked_targets.append(normalized_item)

        return {
            "target_scope": normalized_scope,
            "ranked_targets": normalized_ranked_targets,
            "open_questions": _normalize_string_list(payload.get("open_questions")),
            "confidence": str(payload.get("confidence") or "").strip() or "medium",
            "analysis_mode": str(payload.get("analysis_mode") or "").strip()
            or "llm_constrained",
        }


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        candidate = str(item).strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def _require_text(value: object, field_name: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError(f"{field_name} is required")
    return candidate
