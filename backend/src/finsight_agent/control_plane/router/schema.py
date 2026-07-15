from __future__ import annotations

from typing import Any

from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


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
    if not isinstance(payload["needs"], list):
        raise ValueError("needs must be list")
    if not isinstance(payload["constraints"], dict):
        raise ValueError("constraints must be object")

    # 规范化 entities：兼容新旧两种格式，统一输出下游易用的扁平视图
    normalized_entities = _normalize_entities(payload["entities"])

    return RouterResult(
        intent=payload["intent"],
        follow_up_type=payload["follow_up_type"],
        confidence=payload["confidence"],
        entities=normalized_entities,
        needs=payload["needs"],
        constraints=payload["constraints"],
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
    if isinstance(company_raw, dict):
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
    if isinstance(metric_raw, dict):
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
    if isinstance(time_raw, dict):
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

    # 保留 entities 中其他未识别字段（如 event/themes/topics 等）
    for key, value in raw.items():
        if key not in ("company", "metric", "time_scope"):
            result[key] = value

    return result
