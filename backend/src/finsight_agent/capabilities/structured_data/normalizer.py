from __future__ import annotations

from decimal import Decimal, InvalidOperation


_METRIC_ALIASES = {
    "营业收入": "revenue",
    "归属于上市公司股东的净利润": "net_profit",
    "归母净利润": "net_profit",
    "扣除非经常性损益后的净利润": "deducted_net_profit",
    "经营活动产生的现金流量净额": "operating_cash_flow",
}


def normalize_metric_name(label: str) -> str | None:
    """把常见中文财务指标名归一化为内部标准名。"""

    return _METRIC_ALIASES.get(label.strip())


def normalize_time_scope(*, doc_type: str, report_year: int) -> str:
    """把报告类型与年份归一化为内部期间标识。"""

    if doc_type == "annual_report":
        return f"{report_year}_annual"
    if doc_type == "semiannual_report":
        return f"{report_year}_semiannual"
    return "latest"


def normalize_numeric_text(raw_value: str) -> str:
    """清洗财务表格里的数字文本。"""

    cleaned = raw_value.strip().replace(",", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return format(Decimal(cleaned), "f")
    except InvalidOperation:
        return cleaned
