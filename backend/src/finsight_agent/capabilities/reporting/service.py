from __future__ import annotations

from pathlib import Path
from typing import cast

from shared.contracts.final_response import FinalResponse
from shared.contracts.report_block import (
    EvidenceOverviewBlock,
    EvidenceOverviewItem,
    ReportBlock,
)
from shared.enums.response_mode import ResponseMode
from shared.enums.response_type import ResponseType

from .final_answer_writer import FinalAnswerWriter


class ReportingService:
    """Reporting service with optional LLM-written final answer."""

    def __init__(
        self,
        *,
        llm_client=None,
        final_answer_writer: FinalAnswerWriter | None = None,
    ) -> None:
        prompts_dir = Path(__file__).parent / "prompts"
        if final_answer_writer is not None:
            self._final_answer_writer = final_answer_writer
        else:
            self._final_answer_writer = FinalAnswerWriter(llm_client=llm_client)
        # 按 response_mode 分发不同 prompt：
        # - direct: 泛财经常识直答（不要求证据）
        # - event_answer: 事件背景组织（基于 collect_event_context 结果）
        # - brief_answer: 指标简短答复（基于 query_structured_data 结果）
        # - report: 基于证据的完整报告（保留默认 system.txt）
        self._writers: dict[str, FinalAnswerWriter] = {
            ResponseMode.DIRECT.value: FinalAnswerWriter(
                llm_client=llm_client,
                system_prompt_path=prompts_dir / "direct_answer.txt",
                prompt_name="direct_answer",
            ),
            ResponseMode.EVENT_ANSWER.value: FinalAnswerWriter(
                llm_client=llm_client,
                system_prompt_path=prompts_dir / "event_answer.txt",
                prompt_name="event_answer",
            ),
            ResponseMode.BRIEF_ANSWER.value: FinalAnswerWriter(
                llm_client=llm_client,
                system_prompt_path=prompts_dir / "brief_answer.txt",
                prompt_name="brief_answer",
            ),
            ResponseMode.REPORT.value: FinalAnswerWriter(
                llm_client=llm_client,
                system_prompt_path=prompts_dir / "report_answer.txt",
                prompt_name="report_answer",
            ),
        }

    def build_response(
        self,
        *,
        response_mode: str,
        session_id: str,
        summary: str,
        final_answer_context: dict[str, object] | None = None,
        report_blocks: list[ReportBlock] | None = None,
        uncertainty_notes: list[str] | None = None,
        next_actions: list[str] | None = None,
    ) -> FinalResponse:
        """统一入口：按 response_mode 决定是否拼装 report_blocks 与选择 prompt。

        - direct: 走 direct_answer_writer（泛财经常识直答，不要求证据）
        - brief_answer / event_answer / report: 走 final_answer_writer（基于证据组织回答）
        """
        notes = list(uncertainty_notes or [])
        actions = list(next_actions or [])
        if response_mode == ResponseMode.REPORT.value and report_blocks:
            normalized_blocks = [
                self._validate_report_block(block) for block in report_blocks
            ]
        else:
            normalized_blocks = []
        answer_markdown = self._build_answer_markdown(
            response_mode=response_mode,
            summary=summary,
            uncertainty_notes=notes,
            next_actions=actions,
            final_answer_context=final_answer_context,
        )
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            answer_markdown=answer_markdown,
            report_blocks=normalized_blocks,
            uncertainty_notes=notes,
            next_actions=actions,
        )

    def build_brief_response(
        self,
        session_id: str,
        summary: str,
        *,
        final_answer_context: dict[str, object] | None = None,
    ) -> FinalResponse:
        return self.build_response(
            response_mode=ResponseMode.BRIEF_ANSWER.value,
            session_id=session_id,
            summary=summary,
            final_answer_context=final_answer_context,
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
        return self.build_response(
            response_mode=ResponseMode.REPORT.value,
            session_id=session_id,
            summary=summary,
            final_answer_context=final_answer_context,
            report_blocks=report_blocks,
            uncertainty_notes=uncertainty_notes,
            next_actions=next_actions,
        )

    def _build_answer_markdown(
        self,
        *,
        response_mode: str,
        summary: str,
        uncertainty_notes: list[str],
        next_actions: list[str],
        final_answer_context: dict[str, object] | None,
    ) -> str:
        if final_answer_context:
            writer = self._writers.get(response_mode, self._final_answer_writer)
            try:
                context = dict(final_answer_context)
                context.setdefault("summary", summary)
                context.setdefault("uncertainty_notes", list(uncertainty_notes))
                context.setdefault("next_actions", list(next_actions))
                draft = writer.write_answer(
                    final_answer_context=context
                )
                return draft.answer_markdown
            except Exception:  # noqa: BLE001
                return self._fallback_answer_markdown(
                    summary=summary,
                    uncertainty_notes=uncertainty_notes,
                    next_actions=next_actions,
                    degraded=True,
                )
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
        degraded: bool = False,
    ) -> str:
        parts = [summary.strip()]
        if degraded:
            parts.append(
                "> ⚠️ LLM 生成失败，以上为降级摘要。请检查 AGICTO_API_KEY 配置与额度。"
            )
        if uncertainty_notes:
            parts.append(
                "Notes: " + "; ".join(str(item).strip() for item in uncertainty_notes if str(item).strip())
            )
        if next_actions:
            parts.append(
                "Next: " + "; ".join(str(item).strip() for item in next_actions if str(item).strip())
            )
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
