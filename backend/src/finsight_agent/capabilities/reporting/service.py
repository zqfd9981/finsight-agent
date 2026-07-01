from __future__ import annotations

from typing import cast

from shared.contracts.final_response import FinalResponse
from shared.contracts.report_block import (
    EvidenceOverviewBlock,
    EvidenceOverviewItem,
    ReportBlock,
)
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
        report_blocks: list[ReportBlock],
        uncertainty_notes: list[str],
        next_actions: list[str],
    ) -> FinalResponse:
        """构造最小 report 响应对象。"""
        normalized_blocks = [self._validate_report_block(block) for block in report_blocks]
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            report_blocks=normalized_blocks,
            uncertainty_notes=list(uncertainty_notes),
            next_actions=list(next_actions),
        )

    def _validate_report_block(self, block: ReportBlock) -> ReportBlock:
        if block.get("block_type") != "evidence_overview":
            raise ValueError("unsupported report block type")

        title = block.get("title")
        items = block.get("items")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("evidence_overview block requires title")
        if not isinstance(items, list):
            raise ValueError("evidence_overview block requires items")

        normalized_items: list[EvidenceOverviewItem] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("evidence_overview items must be objects")

            evidence_id = item.get("evidence_id")
            excerpt = item.get("excerpt")
            company_name = item.get("company_name")
            doc_type = item.get("doc_type")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (evidence_id, excerpt, company_name, doc_type)
            ):
                raise ValueError("evidence_overview item fields are required")

            normalized_items.append(
                EvidenceOverviewItem(
                    evidence_id=evidence_id,
                    excerpt=excerpt,
                    company_name=company_name,
                    doc_type=doc_type,
                )
            )

        return cast(
            ReportBlock,
            EvidenceOverviewBlock(
                block_type="evidence_overview",
                title=title,
                items=normalized_items,
            ),
        )
