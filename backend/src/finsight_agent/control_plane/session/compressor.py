from __future__ import annotations


def build_history_summary(
    *,
    intent: str,
    active_topic: str,
    active_candidates: list[str],
    has_evidence_refs: bool,
    previous_summary: str = "",
) -> str:
    """基于结构化字段生成首版模板化历史摘要。"""

    current_summary = ""
    if intent == "metric_lookup":
        readable_topic = _to_readable_topic(active_topic)
        current_summary = f"上一轮已完成{readable_topic}查询，并返回结构化简答。"
        return _merge_history_summary(previous_summary, current_summary)

    if intent == "evidence_lookup":
        candidate_text = "、".join(active_candidates)
        if has_evidence_refs:
            current_summary = (
                f"上一轮已围绕{active_topic}继续展开，"
                f"当前候选对象包括{candidate_text}，并已补充关键证据引用。"
            )
            return _merge_history_summary(previous_summary, current_summary)
        current_summary = f"上一轮已围绕{active_topic}继续展开，当前候选对象包括{candidate_text}。"
        return _merge_history_summary(previous_summary, current_summary)

    if intent == "event_impact_analysis":
        candidate_text = "、".join(active_candidates)
        if candidate_text:
            current_summary = f"上一轮已完成{active_topic}分析，当前候选对象包括{candidate_text}。"
            return _merge_history_summary(previous_summary, current_summary)
        current_summary = f"上一轮已完成{active_topic}分析。"
        return _merge_history_summary(previous_summary, current_summary)

    return ""


def _merge_history_summary(
    previous_summary: str,
    current_summary: str,
    *,
    max_length: int = 120,
) -> str:
    previous = previous_summary.strip()
    current = current_summary.strip()

    if not previous:
        return current[:max_length]
    if current in previous:
        return previous[:max_length]

    merged = f"{previous}；{current}"
    if len(merged) <= max_length:
        return merged

    previous_tail = _last_sentence(previous)
    trimmed = f"{previous_tail}；{current}"
    if len(trimmed) <= max_length:
        return trimmed

    return current[:max_length]


def _last_sentence(summary: str) -> str:
    normalized = summary.strip("；。 ")
    if not normalized:
        return ""

    for separator in ("；", "。"):
        parts = [item.strip() for item in normalized.split(separator) if item.strip()]
        if len(parts) >= 2:
            return f"{parts[-1]}。"
    return f"{normalized}。"


def _to_readable_topic(active_topic: str) -> str:
    readable = active_topic
    readable = readable.replace("net_profit", "净利润").replace("revenue", "营收")
    readable = readable.replace("_annual", " 年")
    readable = readable.replace(" 年 ", " 年")
    return readable
