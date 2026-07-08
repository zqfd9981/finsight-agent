from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnalysisStreamEvent:
    version: str = "v1"
    event_type: str = ""
    run_id: str = ""
    stage_name: str = ""
    status: str = ""
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    final_response: dict[str, Any] | None = None
