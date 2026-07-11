from __future__ import annotations

import re

from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


_COMPANY_PATTERN = re.compile(r"(宁德时代|贵州茅台|比亚迪|中远海能|招商轮船)")
_YEAR_PATTERN = re.compile(r"(20\d{2})\s*年")
_METRIC_KEYWORDS = {
    "净利润": "net_profit",
    "营收": "revenue",
    "收入": "revenue",
}


def route_with_rules(
    normalized_query: str,
    session_context: SessionContext | None,
    follow_up_type: str,
) -> RouterResult:
    if _is_out_of_scope(normalized_query):
        return RouterResult(
            intent=Intent.OUT_OF_SCOPE.value,
            follow_up_type=follow_up_type,
            confidence="high",
            entities={"query": normalized_query},
            needs=[],
            constraints={
                "preferred_output": "guardrail",
                "reason_code": "out_of_scope_request",
            },
        )

    if _looks_like_evidence_lookup(normalized_query, session_context):
        return RouterResult(
            intent=Intent.EVIDENCE_LOOKUP.value,
            follow_up_type=follow_up_type,
            confidence="high",
            entities={
                "target": _extract_target(normalized_query, session_context),
                "claim": normalized_query,
            },
            needs=["rag_retrieval"],
            constraints={
                "preferred_output": "report",
                "retrieval_budget": 4,
            },
        )

    if _looks_like_event_analysis(normalized_query):
        return RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=follow_up_type,
            confidence="high",
            entities={
                "event": _extract_event(normalized_query),
                "themes": _extract_themes(normalized_query),
                "time_scope": _extract_event_time_scope(normalized_query),
            },
            needs=["news_search", "concept_mapping", "rag_retrieval"],
            constraints={
                "time_hint": _extract_event_time_scope(normalized_query),
                "preferred_output": "report",
            },
        )

    if _looks_like_metric_lookup(normalized_query):
        return RouterResult(
            intent=Intent.METRIC_LOOKUP.value,
            follow_up_type=follow_up_type,
            confidence="high",
            entities={
                "company": _extract_company(normalized_query),
                "metric": _extract_metric(normalized_query),
                "time_scope": _extract_metric_time_scope(normalized_query),
            },
            needs=["structured_data_query"],
            constraints={"preferred_output": "brief_answer"},
        )

    # 兜底：金融领域但不属于 metric/event/evidence 任一类型 → 泛财经轻路径（LLM 直答）
    return RouterResult(
        intent=Intent.GENERAL_FINANCE_QA.value,
        follow_up_type=follow_up_type,
        confidence="medium",
        entities={
            "query": normalized_query,
            "topics": _extract_topics(normalized_query),
        },
        needs=["direct_llm"],
        constraints={"preferred_output": "direct"},
    )


def detect_follow_up_type(
    query: str,
    session_context: SessionContext | None,
) -> str:
    if session_context is None or not session_context.session_id:
        return FollowUpType.NONE.value

    if any(keyword in query for keyword in ("对比", "比较", "谁更", "差异")):
        return FollowUpType.COMPARE.value
    if any(keyword in query for keyword in ("展开", "证据", "依据", "原文", "出处", "同比变化原因")):
        return FollowUpType.DRILLDOWN.value
    if any(keyword in query for keyword in ("继续", "延伸", "还有哪些", "再看看")):
        return FollowUpType.EXPAND.value
    if _topic_switched(query, session_context):
        return FollowUpType.REDIRECT.value
    return FollowUpType.NONE.value


def _topic_switched(query: str, session_context: SessionContext) -> bool:
    active_topic = session_context.active_topic
    if not active_topic:
        return False

    if "航运" in active_topic and any(company in query for company in ("贵州茅台", "宁德时代", "比亚迪")):
        return True
    if "净利润" in active_topic and "航运" in query:
        return True
    return False


def _looks_like_metric_lookup(query: str) -> bool:
    return (
        _extract_company(query) is not None
        and _extract_metric(query) is not None
        and any(token in query for token in ("多少", "是多少", "多大", "营收", "净利润"))
    )


def _looks_like_event_analysis(query: str) -> bool:
    return any(keyword in query for keyword in ("利好哪些", "受益", "影响哪些", "航运公司", "板块"))


def _looks_like_evidence_lookup(
    query: str,
    session_context: SessionContext | None,
) -> bool:
    evidence_keywords = ("证据", "依据", "原文", "出处", "展开", "同比变化原因")
    if any(keyword in query for keyword in evidence_keywords):
        return True
    if session_context and session_context.active_candidates:
        return any(keyword in query for keyword in ("对比", "比较", "谁更", "差异"))
    return False


def _is_out_of_scope(query: str) -> bool:
    """只拦截真正不支持的：投资建议/荐股类。泛财经常识问题不再被打成 out_of_scope。"""
    return any(keyword in query for keyword in ("股价", "估值模型", "目标价", "下周走势", "短线", "推荐买", "荐股"))


def _extract_topics(query: str) -> list[str]:
    """从泛财经 query 中抽取主题词，供 direct_answer prompt 使用。"""
    topics: list[str] = []
    finance_keywords = {
        "汇率": "汇率",
        "贬值": "汇率",
        "升值": "汇率",
        "降息": "货币政策",
        "加息": "货币政策",
        "通胀": "通胀",
        "利率": "利率",
        "债市": "债市",
        "股市": "股市",
        "航运": "航运",
        "半导体": "半导体",
        "原油": "原油",
        "黄金": "黄金",
    }
    for keyword, topic in finance_keywords.items():
        if keyword in query and topic not in topics:
            topics.append(topic)
    if not topics:
        topics.append("泛金融")
    return topics


def _extract_company(query: str) -> str | None:
    match = _COMPANY_PATTERN.search(query)
    return match.group(1) if match else None


def _extract_metric(query: str) -> str | None:
    for keyword, metric in _METRIC_KEYWORDS.items():
        if keyword in query:
            return metric
    return None


def _extract_metric_time_scope(query: str) -> str:
    year_match = _YEAR_PATTERN.search(query)
    if year_match:
        return f"{year_match.group(1)}_annual"
    return "latest"


def _extract_event(query: str) -> str:
    if "红海" in query:
        return "红海局势升级"
    return query


def _extract_themes(query: str) -> list[str]:
    themes: list[str] = []
    if "航运" in query:
        themes.append("航运")
    if "油运" in query:
        themes.append("油运")
    if not themes:
        themes.append("泛主题")
    return themes


def _extract_event_time_scope(query: str) -> str:
    if any(keyword in query for keyword in ("近期", "最近", "当前", "升级")):
        return "recent"
    return "unspecified"


def _extract_target(
    query: str,
    session_context: SessionContext | None,
) -> str:
    companies = [company for company in ("中远海能", "招商轮船", "宁德时代", "贵州茅台") if company in query]
    if len(companies) >= 2:
        return " vs ".join(companies[:2])
    if len(companies) == 1:
        return companies[0]
    if session_context and session_context.active_candidates:
        if len(session_context.active_candidates) >= 2 and "对比" in query:
            return " vs ".join(session_context.active_candidates[:2])
        return session_context.active_candidates[0]
    return "unknown_target"
