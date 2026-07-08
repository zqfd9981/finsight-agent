from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from finsight_agent.config.settings import load_settings
from finsight_agent.infra.llm.client import LlmClient


@dataclass(slots=True)
class FinalAnswerDraft:
    answer_markdown: str
    answer_confidence: str = ""


class FinalAnswerWriter:
    """LLM-backed final answer generator with externally managed prompts."""

    def __init__(
        self,
        *,
        llm_client: LlmClient | None = None,
        system_prompt_path: Path | None = None,
    ) -> None:
        settings = load_settings()
        resolved_prompt_path = (
            system_prompt_path
            or settings.reporting.prompts.final_answer_writer_system_prompt_path
        )
        self._system_prompt = resolved_prompt_path.read_text(encoding="utf-8")
        self._llm_client = llm_client or LlmClient()

    def write_answer(
        self,
        *,
        final_answer_context: dict[str, object],
    ) -> FinalAnswerDraft:
        payload = self._llm_client.complete_json(
            prompt_name="final_answer_writer",
            variables={
                "system_prompt": self._system_prompt,
                "final_answer_context": final_answer_context,
            },
        )
        answer_markdown = str(payload.get("answer_markdown") or "").strip()
        if not answer_markdown:
            raise ValueError("final answer writer returned empty answer_markdown")
        return FinalAnswerDraft(
            answer_markdown=answer_markdown,
            answer_confidence=str(payload.get("answer_confidence") or "").strip(),
        )
