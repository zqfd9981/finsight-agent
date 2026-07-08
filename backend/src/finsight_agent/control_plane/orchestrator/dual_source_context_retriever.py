from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from finsight_agent.capabilities.rerank import (
    RerankCandidate,
    build_default_reranker,
)
from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.context_retriever import (
    ExternalContextRetriever,
)


_BLACKLISTED_HOST_KEYWORDS = (
    "zhidao.baidu.com",
    "wen.baidu.com",
    "wenwen.sogou.com",
    "guba.eastmoney.com",
)
_NOISY_TEXT_KEYWORDS = (
    "开户链接",
    "app下载",
    "广告",
    "推广",
    "点击下载",
)
_QUERY_SPLIT_MARKERS = (
    "到底",
    "意味着",
    "如何",
    "怎么",
    "哪些",
    "什么",
    "影响",
    "会",
    "对",
)


class DualSourceExternalContextRetriever(ExternalContextRetriever):
    """Merge, filter, and rerank external event/disclosure candidates."""

    def __init__(
        self,
        *,
        planner,
        event_search_provider,
        disclosure_search_provider,
        reranker=None,
        min_event_candidate_count: int = 8,
        min_disclosure_candidate_count: int = 5,
        selected_candidate_limit: int = 3,
    ) -> None:
        self._planner = planner
        self._event_search_provider = event_search_provider
        self._disclosure_search_provider = disclosure_search_provider
        self._reranker = reranker or build_default_reranker()
        self._min_event_candidate_count = max(1, min_event_candidate_count)
        self._min_disclosure_candidate_count = max(1, min_disclosure_candidate_count)
        self._selected_candidate_limit = max(1, selected_candidate_limit)

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
        strategy: str,
    ) -> dict[str, object] | None:
        router_payload = {
            "intent": "event_impact_analysis",
            "entities": {
                "event": event,
                "themes": themes,
                "time_scope": time_scope,
            },
        }
        plan = self._planner.build_plan(
            strategy_payload={"strategy": strategy},
            router_payload=router_payload,
        )

        merged = ExternalContextResult(
            source_status={
                "mode": plan.mode or strategy,
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

        selected_items, source_status = self._select_items(
            query=query,
            items=merged.items,
            source_status=merged.source_status,
            limit=max(limit, self._selected_candidate_limit),
        )
        if merged.items:
            candidate_hints = self._merge_list(
                merged.candidate_hints,
                [
                    *[name for item in selected_items for name in item.company_names],
                    *[theme for item in selected_items for theme in item.themes],
                ],
            )
            evidence_refs = [
                item.evidence_ref for item in selected_items if item.evidence_ref
            ]
            supporting_points = self._deduplicate_text(
                [(item.snippet or item.title).strip() for item in selected_items]
            )[:3]
            summary_hint = selected_items[0].title if selected_items else ""
        else:
            candidate_hints = list(merged.candidate_hints)
            evidence_refs = list(merged.evidence_refs)
            supporting_points = list(merged.supporting_points)
            summary_hint = merged.summary_hint

        if not summary_hint and not evidence_refs and not source_status:
            return None

        return {
            "summary_hint": summary_hint,
            "supporting_points": supporting_points,
            "evidence_refs": evidence_refs,
            "candidate_hints": candidate_hints,
            "source_status": source_status,
            "items": [self._serialize_item(item) for item in selected_items],
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
            fetch_limit = max(limit, self._min_event_candidate_count)
            return self._event_search_provider.search_event_context(
                query=query,
                event=event,
                themes=themes,
                time_scope=time_scope,
                limit=fetch_limit,
            )
        if source == "disclosure_search":
            disclosure_query = " ".join(
                part for part in (query, event, " ".join(themes)) if part
            ).strip()
            fetch_limit = max(limit, self._min_disclosure_candidate_count)
            return self._disclosure_search_provider.search(
                query=disclosure_query,
                limit=fetch_limit,
            )
        return None

    def _select_items(
        self,
        *,
        query: str,
        items: list[ExternalContextItem],
        source_status: dict[str, object],
        limit: int,
    ) -> tuple[list[ExternalContextItem], dict[str, object]]:
        raw_count = len(items)
        filtered_items = self._filter_items(items)
        status = dict(source_status)
        status.update(
            {
                "candidate_count": raw_count,
                "filtered_candidate_count": len(filtered_items),
                "rerank_backend": getattr(self._reranker, "backend_name", "custom_reranker"),
            }
        )
        if not filtered_items:
            status["topic_mismatch"] = bool(raw_count)
            return [], status

        candidates = [
            RerankCandidate(
                id=str(index),
                title=item.title,
                text=self._compose_candidate_text(item),
                metadata={
                    "source": item.source,
                    "url": item.url,
                    "publish_date": item.publish_date,
                },
            )
            for index, item in enumerate(filtered_items)
        ]
        rerank_results = self._reranker.rerank(
            query=query,
            profile="external_news",
            candidates=candidates,
            top_n=limit,
        )
        score_map = {
            str(result["id"]) if isinstance(result, dict) else result.id: result
            for result in rerank_results
        }

        selected_items: list[ExternalContextItem] = []
        anchors = _extract_query_anchors(query)
        for index, item in enumerate(filtered_items):
            score_entry = score_map.get(str(index))
            if score_entry is None:
                continue
            keep = bool(score_entry["keep"]) if isinstance(score_entry, dict) else bool(score_entry.keep)
            if not keep:
                continue
            if anchors and not _contains_anchor(self._compose_candidate_text(item), anchors):
                continue
            selected_items.append(item)
            if len(selected_items) >= limit:
                break

        if not selected_items and rerank_results:
            status["topic_mismatch"] = True
        status["selected_candidate_count"] = len(selected_items)
        return selected_items, status

    def _filter_items(self, items: list[ExternalContextItem]) -> list[ExternalContextItem]:
        filtered: list[ExternalContextItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            title = item.title.strip()
            text = self._compose_candidate_text(item)
            if not title or not text:
                continue
            if _looks_low_quality(text):
                continue
            if _is_blacklisted_url(item.url):
                continue
            dedupe_key = (title, item.url.strip())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            filtered.append(item)
        return filtered

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
    def _compose_candidate_text(item: ExternalContextItem) -> str:
        return " ".join(part for part in (item.title, item.snippet) if part).strip()

    @staticmethod
    def _serialize_item(item: ExternalContextItem) -> dict[str, Any]:
        return {
            "title": item.title,
            "source": item.source,
            "publish_date": item.publish_date,
            "url": item.url,
            "snippet": item.snippet,
            "evidence_ref": item.evidence_ref,
            "company_names": list(item.company_names),
            "company_codes": list(item.company_codes),
            "themes": list(item.themes),
        }

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

    @staticmethod
    def _deduplicate_text(parts: list[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for part in parts:
            normalized = part.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged


def _is_blacklisted_url(url: str) -> bool:
    hostname = urlparse(url).netloc.lower()
    if not hostname:
        return False
    return any(keyword in hostname for keyword in _BLACKLISTED_HOST_KEYWORDS)


def _looks_low_quality(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in _NOISY_TEXT_KEYWORDS)


def _extract_query_anchors(query: str) -> list[str]:
    compact = query.strip()
    if not compact:
        return []
    segment = compact
    for marker in _QUERY_SPLIT_MARKERS:
        position = segment.find(marker)
        if position > 0:
            segment = segment[:position]
            break
    segment = "".join(character for character in segment if character.isalnum() or "\u4e00" <= character <= "\u9fff")
    if len(segment) < 2:
        return []
    anchors: list[str] = []
    for size in range(min(4, len(segment)), 1, -1):
        anchor = segment[:size]
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    return anchors


def _contains_anchor(text: str, anchors: list[str]) -> bool:
    normalized = text.strip()
    return any(anchor in normalized for anchor in anchors)
