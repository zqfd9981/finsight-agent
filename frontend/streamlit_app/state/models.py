from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EventEvalCaseView:
    case_id: str
    query: str
    expected_intent: str
    expected_strategy: str
    allow_degraded: bool
    min_target_count: int
    expected_target_keywords: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(slots=True)
class EventReplayResultView:
    case_id: str
    query: str
    actual_intent: str
    actual_strategy: str
    response_type: str
    degraded: bool
    target_count: int
    evidence_ref_count: int
    summary: str
    failure_reason: str | None
    target_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EventReplayRecordView:
    case_id: str
    query: str
    result: EventReplayResultView
    checks: list[dict[str, str]]


@dataclass(slots=True)
class EventReplaySummaryView:
    total: int
    pass_count: int
    warn_count: int
    fail_count: int


@dataclass(slots=True)
class EventReplayRunView:
    summary: EventReplaySummaryView
    records: list[EventReplayRecordView]
