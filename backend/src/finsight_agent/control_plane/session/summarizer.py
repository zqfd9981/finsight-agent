"""会话历史 LLM 压缩器。

当 ``SessionContext.turns`` 超过 3 轮时，把最早的 1 轮 + 旧
``history_summary`` 压缩成新的 ``history_summary``，保留关键公司、
指标与数值结论。

设计目标：
- 控制摘要 ≤ 150 字符
- 保留用户关注的公司、查询的指标、关键数值结论
- 失败时回退到模板化摘要，不阻塞主流程
"""

from __future__ import annotations

import json
import logging
from typing import Any

from finsight_agent.infra.llm import LlmClient
from finsight_agent.infra.llm.prompt_registry import get_prompt
from shared.contracts.session_context import ConversationTurn

_logger = logging.getLogger(__name__)

# 摘要最大长度（字符）
_MAX_SUMMARY_LENGTH = 150


def summarize_history(
    *,
    llm_client: LlmClient | None,
    existing_summary: str,
    turns_to_compress: list[ConversationTurn],
) -> str:
    """把 ``turns_to_compress`` + ``existing_summary`` 压缩成新摘要。

    Args:
        llm_client: LLM 客户端，None 时回退到模板化摘要
        existing_summary: 旧的 history_summary
        turns_to_compress: 待压缩的轮次（通常是 turns 列表最早 1 轮）

    Returns:
        新的 history_summary 字符串
    """
    if not turns_to_compress:
        return existing_summary[:_MAX_SUMMARY_LENGTH]

    turns_text = _format_turns_for_prompt(turns_to_compress)

    # LLM 不可用时回退到模板化摘要
    if llm_client is None:
        return _fallback_summary(existing_summary, turns_to_compress)

    try:
        # 从集中 prompts/ 目录加载 prompt 文本
        system_prompt = get_prompt("session.summarizer").render(
            existing_summary=existing_summary,
            turns_text=turns_text,
        )
        payload = llm_client.complete_json(
            prompt_name="session_summarizer",
            variables={
                "existing_summary": existing_summary,
                "turns_text": turns_text,
                "system_prompt": system_prompt,
            },
        )
        summary = str(payload.get("summary") or "").strip()
        if summary:
            return summary[:_MAX_SUMMARY_LENGTH]
        return _fallback_summary(existing_summary, turns_to_compress)
    except Exception as exc:
        _logger.warning("LLM 历史摘要失败，回退到模板化摘要: %s", exc)
        return _fallback_summary(existing_summary, turns_to_compress)


def _format_turns_for_prompt(turns: list[ConversationTurn]) -> str:
    """把轮次列表格式化为 prompt 文本。"""
    lines: list[str] = []
    for i, turn in enumerate(turns, start=1):
        entities = turn.entities_snapshot or {}
        company = entities.get("company_name") or entities.get("company", "")
        metric = entities.get("metric_raw") or entities.get("metric", "")
        summary = turn.response_summary[:80] if turn.response_summary else ""
        lines.append(
            f"  - 轮次{i}: query={turn.query!r} intent={turn.intent} "
            f"company={company!r} metric={metric!r} summary={summary!r}"
        )
    return "\n".join(lines)


def _fallback_summary(
    existing_summary: str,
    turns: list[ConversationTurn],
) -> str:
    """模板化摘要兜底（LLM 不可用时用）。"""
    parts: list[str] = []
    if existing_summary.strip():
        parts.append(existing_summary.strip())

    for turn in turns:
        entities = turn.entities_snapshot or {}
        company = entities.get("company_name") or entities.get("company", "")
        metric = entities.get("metric_raw") or entities.get("metric", "")
        if company and metric:
            parts.append(f"早前查询过{company}的{metric}")
        elif company:
            parts.append(f"早前讨论过{company}")
        elif turn.intent:
            parts.append(f"早前进行过{turn.intent}查询")

    summary = "；".join(parts)
    return summary[:_MAX_SUMMARY_LENGTH]
