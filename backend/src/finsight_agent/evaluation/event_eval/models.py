from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EventEvalCase:
    """描述一条事件评测样本。"""

    case_id: str
    query: str
    expected_intent: str
    expected_strategy: str
    allow_degraded: bool
    min_target_count: int = 0
    expected_target_keywords: list[str] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "EventEvalCase":
        return cls(
            case_id=str(payload["case_id"]),
            query=str(payload["query"]),
            expected_intent=str(payload["expected_intent"]),
            expected_strategy=str(payload["expected_strategy"]),
            allow_degraded=bool(payload["allow_degraded"]),
            min_target_count=int(payload.get("min_target_count") or 0),
            expected_target_keywords=[
                str(item).strip()
                for item in (payload.get("expected_target_keywords") or [])
                if str(item).strip()
            ],
            notes=str(payload.get("notes") or "").strip() or None,
        )


@dataclass(slots=True)
class ReplayResult:
    """描述一条事件样本回放后的标准化结果。"""

    case_id: str
    query: str
    actual_intent: str
    actual_strategy: str
    response_type: str
    degraded: bool
    target_count: int
    evidence_ref_count: int
    summary: str
    failure_reason: str | None = None
    target_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "actual_intent": self.actual_intent,
            "actual_strategy": self.actual_strategy,
            "response_type": self.response_type,
            "degraded": self.degraded,
            "target_count": self.target_count,
            "evidence_ref_count": self.evidence_ref_count,
            "summary": self.summary,
            "failure_reason": self.failure_reason,
            "target_keywords": list(self.target_keywords),
        }


@dataclass(slots=True)
class CheckResult:
    """描述单条样本在某个检查项上的评测结果。"""

    check_name: str
    status: str
    message: str
