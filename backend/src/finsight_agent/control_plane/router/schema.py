from __future__ import annotations

import re
from typing import Any

from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent

# 多指标连接词：用于拆分 metric_raw 含"和"/"与"/"等连接词的复合指标
# 例："总资产和负债合计" → ["总资产", "负债合计"]
# 注意：不用"与"因为"与之"等常见词组会误拆；不用"及"因为"及其他"等
_MULTI_METRIC_SPLIT_RE = re.compile(r"[和与]")


def _try_split_multi_metric(metric_dict: dict[str, Any]) -> list[dict[str, Any]] | None:
    """检测 metric.raw 是否含多指标连接词，能拆则返回 list，不能拆返回 None。

    仅当拆出 ≥2 个非空部分时才认为是多指标。每个部分保留原 metric_type
    和 stock_code 等 meta，只替换 raw 字段（standard_name 留空让 normalizer 后续归一化）。

    注意：此函数不验证拆分后的指标是否有效（由 entities_validator 过滤）。
    若拆分后全部无效，validator 会标记 need_fallback，由 service 降级处理。
    """
    raw = str(metric_dict.get("raw") or "").strip()
    if not raw or len(raw) < 4:  # 太短不拆（如"净利润和"无意义）
        return None
    parts = [p.strip() for p in _MULTI_METRIC_SPLIT_RE.split(raw) if p.strip()]
    if len(parts) < 2:
        return None
    # 拆出的每个部分至少 2 字（防止"和"出现在短语中间误拆）
    if any(len(p) < 2 for p in parts):
        return None
    metric_type = str(metric_dict.get("metric_type") or "direct").strip()
    return [
        {"raw": p, "standard_name": "", "metric_type": metric_type}
        for p in parts
    ]


def router_result_from_payload(payload: dict[str, Any]) -> RouterResult:
    required_keys = {
        "intent",
        "follow_up_type",
        "confidence",
        "entities",
        "needs",
        "constraints",
    }
    if not required_keys.issubset(payload):
        raise ValueError("router payload missing required keys")
    if payload["intent"] not in {item.value for item in Intent}:
        raise ValueError("invalid router intent")
    if payload["follow_up_type"] not in {item.value for item in FollowUpType}:
        raise ValueError("invalid follow_up_type")
    if not isinstance(payload["entities"], dict):
        raise ValueError("entities must be object")
    # 容错 LLM 偶发输出偏差：needs 字符串包装成单元素列表，None/缺失 → 空列表
    raw_needs = payload["needs"]
    if isinstance(raw_needs, str):
        needs = [raw_needs] if raw_needs else []
    elif isinstance(raw_needs, list):
        needs = raw_needs
    else:
        needs = []
    # constraints None/缺失 → 空 dict
    raw_constraints = payload["constraints"]
    if not isinstance(raw_constraints, dict):
        raw_constraints = {}

    # 规范化 entities：兼容新旧两种格式，统一输出下游易用的扁平视图
    normalized_entities = _normalize_entities(payload["entities"])

    raw_filters = payload.get("filters")
    raw_ranking = payload.get("ranking")
    return RouterResult(
        intent=payload["intent"],
        follow_up_type=payload["follow_up_type"],
        confidence=payload["confidence"],
        entities=normalized_entities,
        needs=needs,
        constraints=raw_constraints,
        filters=raw_filters if isinstance(raw_filters, list) else [],
        ranking=raw_ranking if isinstance(raw_ranking, dict) else None,
    )


def _normalize_entities(raw: dict[str, Any]) -> dict[str, Any]:
    """规范化 entities 结构。

    支持两种输入格式：
    1. 新格式（嵌套对象）：
       {"company": {"raw": "...", "standard_name": "...", "stock_code": "..."},
        "metric": {"raw": "...", "standard_name": "...", "metric_type": "..."},
        "time_scope": {"raw": "...", "period_end": "...", "fiscal_year": 2024}}
    2. 旧格式（扁平字符串）：
       {"company": "格力电器", "metric": "货币资金", "time_scope": "2024年末"}

    输出统一格式（保留嵌套对象 + 暴露扁平字段便于下游使用）：
       {"company": {"raw": "...", "standard_name": "...", "stock_code": "..."},
        "metric": {"raw": "...", "standard_name": "...", "metric_type": "..."},
        "time_scope": {"raw": "...", "period_end": "...", "fiscal_year": 2024},
        # 扁平字段（下游可直接用）
        "company_name": "格力电器",
        "company_code": "000651",
        "metric_name": "cash_and_equivalents",  # standard_name 优先
        "metric_raw": "货币资金",
        "metric_type": "direct",
        "period_end": "2024-12-31",
        "time_scope_raw": "2024年末"}
    """
    result: dict[str, Any] = {}

    # company
    company_raw = raw.get("company")
    if isinstance(company_raw, list):
        # 新格式列表型：保留 list 供 query_via_assembler 用，扁平字段取第一个
        result["company"] = company_raw
        first = company_raw[0] if company_raw else {}
        if isinstance(first, dict):
            result["company_name"] = str(
                first.get("standard_name") or first.get("raw") or ""
            ).strip()
            result["company_code"] = str(first.get("stock_code") or "").strip()
        else:
            result["company_name"] = str(first or "").strip()
            result["company_code"] = ""
    elif isinstance(company_raw, dict):
        result["company"] = company_raw
        result["company_name"] = str(
            company_raw.get("standard_name") or company_raw.get("raw") or ""
        ).strip()
        result["company_code"] = str(company_raw.get("stock_code") or "").strip()
    else:
        # 旧格式：company 是字符串
        company_str = str(company_raw or "").strip()
        result["company"] = {"raw": company_str, "standard_name": company_str, "stock_code": ""}
        result["company_name"] = company_str
        result["company_code"] = ""

    # metric
    metric_raw = raw.get("metric")
    if isinstance(metric_raw, list):
        result["metric"] = metric_raw
        first = metric_raw[0] if metric_raw else {}
        if isinstance(first, dict):
            result["metric_raw"] = str(first.get("raw") or "").strip()
            result["metric_name"] = str(
                first.get("standard_name") or first.get("raw") or ""
            ).strip()
            result["metric_type"] = str(first.get("metric_type") or "direct").strip()
        else:
            result["metric_raw"] = str(first or "").strip()
            result["metric_name"] = str(first or "").strip()
            result["metric_type"] = "direct"
    elif isinstance(metric_raw, dict):
        # 多指标拆分：metric_raw 含"和"/"与"等连接词时，尝试拆成 list
        # 例："总资产和负债合计" → [{raw:"总资产"}, {raw:"负债合计"}]
        # router LLM 偶尔把复合指标识别成单个 metric，这里做确定性后处理
        split = _try_split_multi_metric(metric_raw)
        if split is not None:
            result["metric"] = split
            first = split[0] if split else {}
            result["metric_raw"] = str(first.get("raw") or "").strip()
            result["metric_name"] = str(
                first.get("standard_name") or first.get("raw") or ""
            ).strip()
            result["metric_type"] = str(first.get("metric_type") or "direct").strip()
        else:
            result["metric"] = metric_raw
            result["metric_raw"] = str(metric_raw.get("raw") or "").strip()
            result["metric_name"] = str(
                metric_raw.get("standard_name") or metric_raw.get("raw") or ""
            ).strip()
            result["metric_type"] = str(metric_raw.get("metric_type") or "direct").strip()
    else:
        # 旧格式：metric 是字符串
        metric_str = str(metric_raw or "").strip()
        result["metric"] = {"raw": metric_str, "standard_name": metric_str, "metric_type": "direct"}
        result["metric_raw"] = metric_str
        result["metric_name"] = metric_str
        result["metric_type"] = "direct"

    # time_scope
    time_raw = raw.get("time_scope")
    if isinstance(time_raw, list):
        result["time_scope"] = time_raw
        first = time_raw[0] if time_raw else {}
        if isinstance(first, dict):
            result["time_scope_raw"] = str(first.get("raw") or "").strip()
            result["period_end"] = str(first.get("period_end") or "").strip()
            fiscal_year = first.get("fiscal_year")
            if fiscal_year is not None:
                try:
                    result["fiscal_year"] = int(fiscal_year)
                except (TypeError, ValueError):
                    pass
        else:
            result["time_scope_raw"] = str(first or "").strip()
            result["period_end"] = ""
    elif isinstance(time_raw, dict):
        result["time_scope"] = time_raw
        result["time_scope_raw"] = str(time_raw.get("raw") or "").strip()
        result["period_end"] = str(time_raw.get("period_end") or "").strip()
        fiscal_year = time_raw.get("fiscal_year")
        if fiscal_year is not None:
            try:
                result["fiscal_year"] = int(fiscal_year)
            except (TypeError, ValueError):
                pass
    else:
        # 旧格式：time_scope 是字符串
        time_str = str(time_raw or "").strip()
        result["time_scope"] = {"raw": time_str, "period_end": "", "fiscal_year": None}
        result["time_scope_raw"] = time_str
        result["period_end"] = ""

    # 保留 entities 中其他未识别字段（如 event/themes/topics/filters/ranking 等）
    for key, value in raw.items():
        if key not in ("company", "metric", "time_scope"):
            result[key] = value

    return result
