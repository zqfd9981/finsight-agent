"""约束校验闸门（2.2 定案）：Router 产出的 filters / ranking 字段经此校验/透传后喂给 assemble。

设计铁律：
- LLM 只产结构化字段，绝不拼 SQL；SQL 字符串永远由 sql_assembler 确定性拼。
- 本模块是 assemble 之前的第二道防线：过滤结构非法 / 不可归一的项，收集 warnings 供可观测。

支持范围（与 sql_assembler.build_value_filter / build_ranking 对齐）：
- filters：阈值筛选。op ∈ {>, <, >=, <=, =, !=}；value 字面数字；unit 单位字符串（默认元）。
- ranking：TopN 排序。{limit: int≥1, desc: bool(默认 True), by_metric?: str}。

不支持（明确降级，避免垃圾进 assemble）：
- 相对值比较（"比 xx 公司高"）：value 应是对另一行的引用而非字面数字 → 校验时因 value
  非数值被丢弃，等价于"省略约束、返回候选集、自然语言兜底"。这是 2.3 缺口，非本模块职责。
"""
from __future__ import annotations

from typing import Any

# 与 sql_assembler._SUPPORTED_OPS 对齐（复用同一组运算符，避免两处漂移）
from .sql_assembler import _SUPPORTED_OPS

_OPS = frozenset(_SUPPORTED_OPS)


def resolve_constraints(
    filters: Any = None,
    ranking: Any = None,
) -> tuple[list[dict], "dict | None", list[str]]:
    """校验并透传 Router 约束字段。

    Returns:
        (clean_filters, clean_ranking, warnings)
        - clean_filters：通过校验的 filter 列表（空列表表示无筛选）。
        - clean_ranking：通过校验的 ranking dict，或 None（无排序）。
        - warnings：被丢弃项的说明，供可观测（不抛异常，降级而非失败）。
    """
    clean_filters, warnings = _resolve_filters(filters)
    clean_ranking, rank_warnings = _resolve_ranking(ranking)
    warnings.extend(rank_warnings)
    return clean_filters, clean_ranking, warnings


def _resolve_filters(filters: Any) -> tuple[list[dict], list[str]]:
    if not filters:
        return [], []
    if not isinstance(filters, list):
        return [], ["filters 非列表，已忽略"]

    clean: list[dict] = []
    warnings: list[str] = []
    for i, item in enumerate(filters):
        if not isinstance(item, dict):
            warnings.append(f"filters[{i}] 非对象，已忽略")
            continue
        op = item.get("op")
        if op not in _OPS:
            warnings.append(f"filters[{i}] 不支持的 op={op!r}，已忽略")
            continue
        # value 必须是字面数字（不支持相对值/公司名引用）——非数值直接丢弃
        try:
            num = float(item.get("value"))
        except (TypeError, ValueError):
            warnings.append(
                f"filters[{i}] value 非数值（{item.get('value')!r}），已忽略"
            )
            continue
        unit = str(item.get("unit", "元") or "元")
        resolved = {"op": op, "value": num, "unit": unit}
        metric = item.get("metric")
        if metric:
            resolved["metric"] = str(metric)
        clean.append(resolved)
    return clean, warnings


def _resolve_ranking(ranking: Any) -> tuple["dict | None", list[str]]:
    if not ranking:
        return None, []
    if not isinstance(ranking, dict):
        return None, ["ranking 非对象，已忽略"]
    raw_limit = ranking.get("limit", 10)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None, [f"ranking.limit 非整数（{raw_limit!r}），已忽略"]
    if limit < 1:
        return None, [f"ranking.limit 必须 ≥1（{limit}），已忽略"]
    desc = bool(ranking.get("desc", True))
    resolved = {"limit": limit, "desc": desc}
    by_metric = ranking.get("by_metric")
    if by_metric:
        resolved["by_metric"] = str(by_metric)
    return resolved, []
