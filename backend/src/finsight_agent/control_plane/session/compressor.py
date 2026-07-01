from __future__ import annotations


def build_history_summary(
    *,
    intent: str,
    active_topic: str,
    active_candidates: list[str],
    has_evidence_refs: bool,
) -> str:
    """基于结构化字段生成首版模板化历史摘要。"""

    if intent == "metric_lookup":
        readable_topic = (
            active_topic.replace("net_profit", "净利润").replace("revenue", "营收")
        )
        return f"上一轮已完成{readable_topic}查询，并返回结构化简答。"

    if intent == "evidence_lookup":
        candidate_text = "、".join(active_candidates)
        if has_evidence_refs:
            return (
                f"上一轮已围绕{active_topic}继续展开，"
                f"当前候选对象包括{candidate_text}，并已补充关键证据引用。"
            )
        return f"上一轮已围绕{active_topic}继续展开，当前候选对象包括{candidate_text}。"

    if intent == "event_impact_analysis":
        candidate_text = "、".join(active_candidates)
        if candidate_text:
            return f"上一轮已完成{active_topic}分析，当前候选对象包括{candidate_text}。"
        return f"上一轮已完成{active_topic}分析。"

    return ""
