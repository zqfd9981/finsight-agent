from __future__ import annotations

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType


class ReportingService:
    """V1 reporting 的最小服务骨架。"""

    def build_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        """构造简短响应占位对象，先不拼复杂报告块。"""
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            report_blocks=[],
            uncertainty_notes=[],
            next_actions=[],
        )

    def build_report_response(
        self,
        session_id: str,
        summary: str,
        report_blocks: list[dict[str, object]],
        uncertainty_notes: list[str],
        next_actions: list[str],
    ) -> FinalResponse:
        """构造最小 report 响应对象。"""
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            report_blocks=list(report_blocks),
            uncertainty_notes=list(uncertainty_notes),
            next_actions=list(next_actions),
        )
