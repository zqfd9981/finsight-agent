from __future__ import annotations

from dataclasses import dataclass, field

from shared.contracts.session_context import SessionContext


@dataclass(slots=True)
class SessionSnapshot:
    """会话模块内部使用的最近一次有效轮次快照。"""

    session_id: str
    last_query: str
    last_query_mode: str
    last_intent: str
    last_follow_up_type: str
    last_plan_stages: list[str] = field(default_factory=list)
    context: SessionContext = field(default_factory=SessionContext)
    updated_at: str = ""
