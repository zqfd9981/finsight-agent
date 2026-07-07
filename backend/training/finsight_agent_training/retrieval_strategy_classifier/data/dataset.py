from __future__ import annotations

from typing import Iterable

LABEL_TO_INDEX: dict[str, int] = {
    "event_primary": 0,
    "disclosure_primary": 1,
    "dual_primary": 2,
}

INDEX_TO_LABEL: dict[int, str] = {idx: label for label, idx in LABEL_TO_INDEX.items()}

DEFAULT_FIELD = "无"


def build_input_text(
    *,
    query: str,
    intent: str,
    event: str,
    themes: Iterable[str],
    target: str,
    time_scope: str,
    session_topic: str,
) -> str:
    """拼接喂给 StructBERT 的序列化模板。

    任何字段为空字符串 / 空列表 / None 一律填 ``"无"``，确保序列结构稳定。
    """
    parts: list[str] = [
        f"[QUERY] {query}",
        f"[INTENT] {intent or DEFAULT_FIELD}",
        f"[EVENT] {event or DEFAULT_FIELD}",
        f"[THEMES] {', '.join(themes) if themes else DEFAULT_FIELD}",
        f"[TARGET] {target or DEFAULT_FIELD}",
        f"[TIME_SCOPE] {time_scope or DEFAULT_FIELD}",
        f"[SESSION_TOPIC] {session_topic or DEFAULT_FIELD}",
    ]
    return " ".join(parts)