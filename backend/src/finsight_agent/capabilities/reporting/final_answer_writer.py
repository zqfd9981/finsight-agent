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
    """LLM-backed final answer generator with externally managed prompts.

    prompt 加载优先级：
    1. PromptRegistry（集中 prompts/ 目录，按 ``reporting.{prompt_name}`` 查找）
    2. system_prompt_path 参数（显式指定文件路径）
    3. settings.reporting.prompts.final_answer_writer_system_prompt_path（旧配置兜底）
    """

    def __init__(
        self,
        *,
        llm_client: LlmClient | None = None,
        system_prompt_path: Path | None = None,
        prompt_name: str = "final_answer_writer",
    ) -> None:
        self._system_prompt = self._load_system_prompt(
            prompt_name=prompt_name,
            system_prompt_path=system_prompt_path,
        )
        self._llm_client = llm_client or LlmClient()
        self._prompt_name = prompt_name

    @staticmethod
    def _load_system_prompt(
        *,
        prompt_name: str,
        system_prompt_path: Path | None,
    ) -> str:
        """优先用 PromptRegistry，回退到文件路径配置。"""
        # 1. 尝试 PromptRegistry（reporting.{prompt_name}）
        try:
            from finsight_agent.infra.llm.prompt_registry import get_prompt
            return get_prompt(f"reporting.{prompt_name}").text
        except Exception:
            pass
        # 2. 显式路径参数
        if system_prompt_path is not None:
            return system_prompt_path.read_text(encoding="utf-8")
        # 3. settings 配置兜底
        settings = load_settings()
        return settings.reporting.prompts.final_answer_writer_system_prompt_path.read_text(
            encoding="utf-8"
        )

    def write_answer(
        self,
        *,
        final_answer_context: dict[str, object],
    ) -> FinalAnswerDraft:
        payload = self._llm_client.complete_json(
            prompt_name=self._prompt_name,
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
