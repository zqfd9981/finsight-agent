from __future__ import annotations

from typing import Protocol


class ExternalContextRetriever(Protocol):
    """External event context retriever."""

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
        """Retrieve normalized event context."""

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        """Discover candidate targets when the pool is insufficient."""


class NullExternalContextRetriever:
    """Safe empty implementation."""

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
        del query, event, themes, time_scope, limit, strategy
        return None

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        del query, event_context, limit
        return None
