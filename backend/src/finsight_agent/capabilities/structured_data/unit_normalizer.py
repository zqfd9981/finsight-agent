"""单位归一工具：把带单位的数值字符串归一到基准单位（元）。

用途：
1. ETL 写入 metric_records 时，按本行 unit 计算 value_numeric（Phase A 新数据强制）。
2. SQL Assembler 的 build_value_filter 把用户阈值（如"1000亿"）归一到元，
   与 value_numeric 比较，杜绝"千元/亿元混存"导致的跨公司静默错答。
3. Phase B 回填脚本扫全表按 unit 补 value_numeric。

基准单位：元（CNY）。支持的人民币单位：元/千元/万元/百万元/亿元。
非数值或未知单位时返回 None（调用方决定降级策略）。

设计原则：
- 只做单位换算，不改写原 value 字段（value 仍存原始字符串，value_numeric 是归一后副本）。
- 复用 mineru_parser._UNIT_RE 的单位枚举，并补充"亿元"（年报 ETL 实际会存"亿元"）。
- 纯函数，无 DB/IO 依赖，便于单测。
"""
from __future__ import annotations

import re
from typing import Optional

# 基准单位：元。所有数值归一到元后存入 value_numeric。
_BASE_UNIT = "元"

# 人民币单位 → 换算到元的倍率。补充"亿元"（mineru_parser._UNIT_RE 未覆盖）。
_UNIT_TO_BASE: dict[str, float] = {
    "元": 1.0,
    "千元": 1_000.0,
    "万元": 10_000.0,
    "百万元": 1_000_000.0,
    "亿元": 100_000_000.0,
}

# 数值清洗：去千分位逗号、去空白、括号负值 (123.45) → -123.45、特殊占位符。
_THOUSANDS_SEP = re.compile(r"[,_\s]")
_PAREN_NEGATIVE = re.compile(r"^\((.+)\)$")
_PLACEHOLDERS = {"", "-", "—", "N/A", "n/a", "NA", "null", "None"}


def _clean_value_string(raw: str) -> Optional[str]:
    """把带千分位/括号/占位符的数值字符串清洗成可 float() 的形式。"""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if s in _PLACEHOLDERS:
        return None
    s = _THOUSANDS_SEP.sub("", s)
    m = _PAREN_NEGATIVE.match(s)
    if m:
        s = "-" + m.group(1)
    return s


def normalize_to_base_unit(value: str, unit: str, currency: str = "CNY") -> Optional[float]:
    """把 (value, unit) 归一到基准单位（元），返回 float 或 None。

    Args:
        value: 原始数值字符串（如 "507.45"、"1,234.56"、"(789.00)"）
        unit: 单位（如 "亿元"、"千元"、"元"、"%"）
        currency: 币种，非 CNY 时返回 None（当前只支持人民币归一）

    Returns:
        归一到元后的 float；无法解析/未知单位/非 CNY 时返回 None。

    Examples:
        >>> normalize_to_base_unit("507.45", "亿元")
        50745000000.0
        >>> normalize_to_base_unit("1234.56", "千元")
        1234560.0
        >>> normalize_to_base_unit("95.2", "%")
        >>> # 百分比无归一意义，返回 None（百分比类指标不走数值比较）
    """
    if currency and currency.upper() != "CNY":
        return None
    cleaned = _clean_value_string(value)
    if cleaned is None:
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None
    factor = _UNIT_TO_BASE.get(unit)
    if factor is None:
        # 未知单位（如 "%"、空串）不参与数值比较，返回 None
        return None
    return num * factor


def is_normalizable(unit: str, currency: str = "CNY") -> bool:
    """判断该 (unit, currency) 是否可归一（用于 ETL 决定是否填 value_numeric）。"""
    if currency and currency.upper() != "CNY":
        return False
    return unit in _UNIT_TO_BASE


# ──────────────────────────────────────────────────────────────
# 展示层换算：元 → 亿元（用于 synthesize / trace 卡片友好展示）
# ──────────────────────────────────────────────────────────────

# 展示单位阈值：归一到元后按阈值选最合适的展示单位。
# 优先用"亿元"（A 股年报最常见），小数值降级到"万元"/"元"避免"0.00 亿元"。
_DISPLAY_THRESHOLDS: list[tuple[float, str, float]] = [
    (1e8, "亿元", 1e8),     # ≥ 1 亿 → 亿元
    (1e4, "万元", 1e4),     # ≥ 1 万 → 万元
    (1.0, "元", 1.0),       # ≥ 1 → 元
]

# 每股类指标：单位应为"元/股"。DB 中可能误存为"元"或"千元"，
# 展示层强制改为"元/股"且不做金额换算（避免 EPS=1.16元 被误判为"≥1元"换算成"1元"）。
_PER_SHARE_METRIC_NAMES: set[str] = {
    "basic_earnings_per_share",
    "diluted_earnings_per_share",
    "basic_eps",
    "diluted_eps",
    "basic_earnings_per_share_from_continuing_operations",
    "basic_and_diluted_earnings_per_share",
    "diluted_eps_rmb",
    "basic_earnings_per_share_yuan_per_share",
    "basic_earnings_per_share_excluding_extraordinary_items",
    "diluted_eps_continuing_operations",
}


def is_per_share_metric(metric_name: str) -> bool:
    """判断 metric_name 是否属于每股类指标（展示单位固定为"元/股"）。"""
    return bool(metric_name) and metric_name in _PER_SHARE_METRIC_NAMES


def format_display_value(
    value: str,
    unit: str,
    currency: str = "CNY",
    metric_name: str = "",
) -> tuple[str, str]:
    """把 (value, unit) 换算成展示友好的 (display_value, display_unit)。

    规则：
    - 每股类指标（metric_name 命中 _PER_SHARE_METRIC_NAMES）：强制单位"元/股"，
      原样返回数值（DB 里 unit 字段可能误存为"元"/"千元"，统一纠正）。
    - CNY 金额类（元/千元/万元/百万元/亿元）：归一到元后按阈值选展示单位
      * ≥ 1 亿 → 亿元（保留2位小数）
      * ≥ 1 万 → 万元（保留2位小数）
      * 否则 → 元（保留2位小数，整数去 .00）
      例：("54006794", "千元") → ("540.07", "亿元")
    - "%" / 空单位 / 非 CNY / 非数值 → 原样返回（不动衍生指标）

    Args:
        value: 原始数值字符串
        unit: 原始单位
        currency: 币种，非 CNY 不换算
        metric_name: 可选，指标英文 key；用于识别每股类指标强制单位"元/股"

    Returns:
        (display_value, display_unit)。无法换算时原样返回输入。

    Examples:
        >>> format_display_value("54006794", "千元")
        ('540.07', '亿元')
        >>> format_display_value("35.20%", "%")
        ('35.20%', '%')
        >>> format_display_value("11.58", "千元", metric_name="basic_earnings_per_share")
        ('11.58', '元/股')
        >>> format_display_value("abc", "元")
        ('abc', '元')
    """
    # 每股类指标：强制单位"元/股"，不参与金额换算
    if metric_name and is_per_share_metric(metric_name):
        # 清洗 value 中的千分位逗号，但保留原始数值语义
        cleaned = _clean_value_string(value)
        if cleaned is not None:
            try:
                num = float(cleaned)
                # 整数去 .00，非整数保留 2 位小数
                if abs(num - round(num)) < 1e-9:
                    return f"{num:.0f}", "元/股"
                return f"{num:.2f}", "元/股"
            except ValueError:
                pass
        return value, "元/股"

    # 衍生指标 / 百分比 / 非 CNY 不换算
    if not is_normalizable(unit, currency):
        return value, unit

    base_value = normalize_to_base_unit(value, unit, currency)
    if base_value is None:
        return value, unit

    # 按阈值选展示单位
    for threshold, display_unit, divisor in _DISPLAY_THRESHOLDS:
        if abs(base_value) >= threshold:
            display_num = base_value / divisor
            # 整数去 .00，非整数保留 2 位小数
            if abs(display_num - round(display_num)) < 1e-9:
                display_value = f"{display_num:.0f}"
            else:
                display_value = f"{display_num:.2f}"
            # 负零修正
            if display_value == "-0":
                display_value = "0"
            return display_value, display_unit

    # fallback：极小数值用元
    display_value = f"{base_value:.2f}"
    if display_value == "-0.00":
        display_value = "0.00"
    return display_value, "元"
