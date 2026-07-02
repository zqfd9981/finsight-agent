from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.context_retriever import (
    ExternalContextRetriever,
)
from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
)


class DualSourceExternalContextRetriever(ExternalContextRetriever):
    """协调事件搜索源与官方披露源，产出统一的外部上下文结果。"""

    def __init__(
        self,
        *,
        classifier,
        planner,
        event_search_provider,
        disclosure_search_provider,
    ) -> None:
        self._classifier = classifier
        self._planner = planner
        self._event_search_provider = event_search_provider
        self._disclosure_search_provider = disclosure_search_provider

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        router_payload = {
            "intent": "event_impact_analysis",
            "entities": {
                "event": event,
                "themes": themes,
                "time_scope": time_scope,
            },
        }
        strategy_payload = self._classifier.classify(
            query=query,
            router_payload=router_payload,
            session_topic="",
        )
        plan = self._planner.build_plan(
            strategy_payload=strategy_payload,
            router_payload=router_payload,
        )

        merged = ExternalContextResult(
            source_status={
                "mode": plan.mode or DEFAULT_RETRIEVAL_STRATEGY,
                "allow_local_rag": plan.allow_local_rag,
            }
        )

        for step in plan.steps:
            payload = self._execute_step(
                source=str(step.get("source", "")),
                query=query,
                event=event,
                themes=themes,
                time_scope=time_scope,
                limit=int(step.get("budget", limit) or limit),
            )
            if payload is None:
                continue
            self._merge_result(merged, payload)

        if not merged.summary_hint and not merged.evidence_refs and not merged.items:
            return None

        return {
            "summary_hint": merged.summary_hint,
            "supporting_points": merged.supporting_points,
            "evidence_refs": merged.evidence_refs,
            "candidate_hints": merged.candidate_hints,
            "source_status": merged.source_status,
        }

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        event = str(event_context.get("event", "") or "")
        themes = event_context.get("themes", [])
        theme_text = " ".join(str(theme) for theme in themes if theme)
        composed_query = " ".join(part for part in (query, event, theme_text) if part).strip()
        if not composed_query:
            return None

        payload = self._disclosure_search_provider.search(
            query=composed_query,
            limit=limit,
        )
        if not payload.candidate_hints and not payload.evidence_refs:
            return None

        return {
            "candidates": payload.candidate_hints,
            "evidence_refs": payload.evidence_refs,
            "source_status": payload.source_status,
        }

    def _execute_step(
        self,
        *,
        source: str,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult | None:
        if source == "event_search":
            return self._event_search_provider.search_event_context(
                query=query,
                event=event,
                themes=themes,
                time_scope=time_scope,
                limit=limit,
            )
        if source == "disclosure_search":
            disclosure_query = " ".join(
                part for part in (query, event, " ".join(themes)) if part
            ).strip()
            return self._disclosure_search_provider.search(
                query=disclosure_query,
                limit=limit,
            )
        return None

    def _merge_result(
        self,
        merged: ExternalContextResult,
        payload: ExternalContextResult,
    ) -> None:
        if payload.summary_hint:
            merged.summary_hint = self._merge_text(merged.summary_hint, payload.summary_hint)
        merged.supporting_points = self._merge_list(
            merged.supporting_points,
            payload.supporting_points,
        )
        merged.evidence_refs = self._merge_list(
            merged.evidence_refs,
            payload.evidence_refs,
        )
        merged.candidate_hints = self._merge_list(
            merged.candidate_hints,
            payload.candidate_hints,
        )
        merged.items.extend(payload.items)
        merged.source_status.update(payload.source_status)

    @staticmethod
    def _merge_text(existing: str, incoming: str) -> str:
        if not existing:
            return incoming
        if not incoming or incoming == existing:
            return existing
        return f"{existing}\n{incoming}"

    @staticmethod
    def _merge_list(existing: list[str], incoming: list[str]) -> list[str]:
        seen = set(existing)
        merged = list(existing)
        for item in incoming:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        return merged
