from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


# 初始公司列表（动态加载的兜底，从 raw_filings 目录读取完整列表）
_FALLBACK_COMPANIES = [
    "宁德时代", "贵州茅台", "比亚迪", "中远海能", "招商轮船",
    "TCL中环", "平安银行", "中兴通讯", "美的集团", "泸州老窖",
]
_YEAR_PATTERN = re.compile(r"(20\d{2})\s*年")
# 路由层只识别关键词，返回中文原文，由 StructuredDataService 用 normalizer 映射到标准 key
_METRIC_KEYWORDS = {
    "净利润": "净利润",
    "营收": "营业收入",
    "营业收入": "营业收入",
    "收入": "营业收入",
    "总资产": "资产总计",
    "资产总计": "资产总计",
    "负债": "负债合计",
    "现金流": "经营活动产生的现金流量净额",
    "每股收益": "基本每股收益",
}


@lru_cache(maxsize=1)
def _get_company_pattern() -> re.Pattern[str]:
    """从 raw_filings 目录动态加载公司列表，构建匹配正则。"""
    repo_root = Path(__file__).resolve().parents[5]
    raw_root = repo_root / "var" / "data" / "raw_filings"
    companies: list[str] = list(_FALLBACK_COMPANIES)
    if raw_root.exists():
        for d in raw_root.iterdir():
            if not d.is_dir():
                continue
            parts = d.name.split("_", 1)
            name = parts[1] if len(parts) > 1 else d.name
            if name and name not in companies:
                companies.append(name)
    # 按长度降序排序，避免短名先匹配（如"长安汽车" vs "长安"）
    companies.sort(key=len, reverse=True)
    return re.compile("(" + "|".join(re.escape(c) for c in companies) + ")")


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
        and any(token in query for token in ("多少", "是多少", "多大", "营收", "净利润", "资产", "负债", "现金流", "每股收益"))
    )


def _looks_like_event_analysis(query: str) -> bool:
    """识别事件影响分析类查询。

    匹配模式：
    - 受益/利好 + 板块/股票
    - 对...有影响 / 影响...哪些
    - 航运股/航运公司/油运股等板块关键词
    - 局势/危机/事件 + 影响
    """
    # 直接关键词
    direct_keywords = (
        "利好哪些", "受益", "影响哪些", "航运公司", "板块",
        "有影响", "影响如何", "受影响",
    )
    if any(keyword in query for keyword in direct_keywords):
        return True
    # 模式：事件类词 + 影响类词
    event_words = ("局势", "危机", "冲突", "事件", "政策", "降息", "加息", "制裁")
    impact_words = ("影响", "受益", "利好", "利空", "冲击")
    if any(w in query for w in event_words) and any(w in query for w in impact_words):
        return True
    # 模式：板块/股票类词
    sector_words = ("航运股", "油运股", "航运板块", "港口股", "军工股", "新能源车")
    if any(w in query for w in sector_words):
        return True
    return False


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
    match = _get_company_pattern().search(query)
    return match.group(1) if match else None


def _extract_metric(query: str) -> str | None:
    for keyword, metric in _METRIC_KEYWORDS.items():
        if keyword in query:
            return metric
    return None


def _extract_metric_time_scope(query: str) -> str:
    """从查询中提取时间范围。

    转换规则：
    - "2024年" → "2024年"（保留中文年份，用于匹配 DB time_scope 字段）
      DB 的 time_scope 存的是表格列头（如"2024年"、"2023年"、"2024年12月31日"），
      period_end 则全是报告截止日（2025年报的 period_end 都是 2024-12-31），
      无法区分本年/上年。用 time_scope LIKE 匹配更准确。
    - 无年份 → "latest"
    """
    year_match = _YEAR_PATTERN.search(query)
    if year_match:
        return year_match.group(1) + "年"
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
