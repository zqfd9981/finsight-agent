from __future__ import annotations

from dataclasses import dataclass, field

from .report_block import ReportBlock


@dataclass(slots=True)
class FinalResponse:
    """V1 面向用户的最终响应契约对象。"""

    version: str = "v1"
    response_type: str = "degraded"
    session_id: str = ""
    summary: str = ""
    answer_markdown: str = ""
    report_blocks: list[ReportBlock] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    notes: str | None = None
    # 自检产物（verify_answer 节点产出，可为空）
    verification: dict | None = None
