from __future__ import annotations

from typing import cast

from shared.contracts.final_response import FinalResponse
from shared.contracts.report_block import (
    EvidenceOverviewBlock,
    EvidenceOverviewItem,
    ReportBlock,
)
from shared.enums.response_type import ResponseType

from .final_answer_writer import FinalAnswerWriter


class ReportingService:
    """V1 reporting service with optional LLM-written final answer."""

    def __init__(self, *, llm_client=None, final_answer_writer: FinalAnswerWriter | None = None) -> None:
        if final_answer_writer is not None:
            self._final_answer_writer = final_answer_writer
        else:
            self._final_answer_writer = FinalAnswerWriter(llm_client=llm_client)

    def build_brief_response(
        self,
        session_id: str,
        summary: str,
        *,
        final_answer_context: dict[str, object] | None = None,
    ) -> FinalResponse:
        answer_markdown = self._build_answer_markdown(
            summary=summary,
            uncertainty_notes=[],
            next_actions=[],
            final_answer_context=final_answer_context,
        )
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            answer_markdown=answer_markdown,
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
        *,
        final_answer_context: dict[str, object] | None = None,
    ) -> FinalResponse:
        normalized_blocks = [self._validate_report_block(block) for block in report_blocks]
        answer_markdown = self._build_answer_markdown(
            summary=summary,
            uncertainty_notes=uncertainty_notes,
            next_actions=next_actions,
            final_answer_context=final_answer_context,
        )
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            answer_markdown=answer_markdown,
            report_blocks=normalized_blocks,
            uncertainty_notes=list(uncertainty_notes),
            next_actions=list(next_actions),
        )

    def _build_answer_markdown(
        self,
        *,
        summary: str,
        uncertainty_notes: list[str],
        next_actions: list[str],
        final_answer_context: dict[str, object] | None,
    ) -> str:
        if final_answer_context:
            try:
                context = dict(final_answer_context)
                context.setdefault("summary", summary)
                context.setdefault("uncertainty_notes", list(uncertainty_notes))
                context.setdefault("next_actions", list(next_actions))
                draft = self._final_answer_writer.write_answer(
                    final_answer_context=context
                )
                return draft.answer_markdown
            except Exception:  # noqa: BLE001
                pass
        return self._fallback_answer_markdown(
            summary=summary,
            uncertainty_notes=uncertainty_notes,
            next_actions=next_actions,
        )

    def _fallback_answer_markdown(
        self,
        *,
        summary: str,
        uncertainty_notes: list[str],
        next_actions: list[str],
    ) -> str:
        parts = [summary.strip()]
        if uncertainty_notes:
            parts.append("需要注意：" + "；".join(str(item).strip() for item in uncertainty_notes if str(item).strip()))
        if next_actions:
            parts.append("如需继续分析：" + "；".join(str(item).strip() for item in next_actions if str(item).strip()))
        return "\n\n".join(part for part in parts if part)

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
