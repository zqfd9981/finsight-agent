from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExternalContextItem:
    title: str
    source: str
    publish_date: str
    url: str
    snippet: str
    company_names: list[str] = field(default_factory=list)
    company_codes: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExternalContextResult:
    items: list[ExternalContextItem] = field(default_factory=list)
    summary_hint: str = ""
    supporting_points: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    candidate_hints: list[str] = field(default_factory=list)
    source_status: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ContextRetrievalPlan:
    mode: str
    steps: list[dict[str, object]]
    allow_local_rag: bool
