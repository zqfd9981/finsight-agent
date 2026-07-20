"""确定性 SQL 组装器：吃 router 列表型 entities → 参数化 SQL。

LLM 永远不碰 SQL 字符串拼接，只产出结构化槽位。本模块解决 SQL 构造的确定性，
不解决 router 实体识别的确定性——后者靠 entities_validator + find_best_match 兜底。

设计原则：
- 占位符绑定，绝不字符串拼接用户输入（company_code/metric_name/period_end/value 全用 ?）。
- 多实体场景用 ROW_NUMBER() OVER (PARTITION BY company_code, period_end) 取每条合并口径唯一行，
  避免裸 ORDER BY ... LIMIT 1 在多公司场景丢数据或混入 parent_only 行。
- source_section 白名单：四表 + unknown，排除 notes（防 key 碰撞）。
- 数值比较走 value_numeric（Phase A 起对新数据强制填），阈值按 unit 归一到元。
- 返回 None 表示 Assembler 无法表达（即席长尾，如 CAGR/连续增长），由 service 转 T2S escape。

不连接 DB，只生成 (sql, params)；执行由 sql_executor 做。
"""
from __future__ import annotations

from typing import Optional

from .unit_normalizer import normalize_to_base_unit

# source_section 白名单：四表 + unknown，排除 notes。
# 与 repository.find_best_match 的 section_filter（include_notes=False）保持一致，
# 修正主 T2S 方案 few-shot 只放 income_statement 漏 balance_sheet/cash_flow 的 bug。
_SECTION_WHITELIST = (
    "source_section IN ('income_statement','cash_flow_statement',"
    "'balance_sheet','equity_statement','unknown')"
)

# statement_type 口径优先级：consolidated(0) > unknown(1) > parent_only(2) > else(1)
# 与 repository._STMT_PRIORITY 保持一致。
_STMT_PRIORITY_CASE = (
    "CASE statement_type "
    "WHEN 'consolidated' THEN 0 "
    "WHEN 'unknown' THEN 1 "
    "WHEN 'parent_only' THEN 2 "
    "ELSE 1 END"
)

# 支持的数值比较运算符
_SUPPORTED_OPS = {">", "<", ">=", "<=", "=", "!="}


def _build_in_clause(column: str, values: list[str]) -> tuple[str, tuple[str, ...]]:
    """生成 `column IN (?, ?, ...)` + 参数。values 必须非空。"""
    placeholders = ",".join("?" for _ in values)
    return f"{column} IN ({placeholders})", tuple(values)


def build_company_filter(codes: list[str]) -> tuple[str, tuple[str, ...]]:
    """company_code IN (?, ...)"""
    return _build_in_clause("company_code", codes)


def build_metric_filter(keys: list[str]) -> tuple[str, tuple[str, ...]]:
    """metric_name IN (?, ...)"""
    return _build_in_clause("metric_name", keys)


def build_period_filter(periods: list[str]) -> tuple[str, tuple[str, ...]]:
    """period_end IN (?, ...)"""
    return _build_in_clause("period_end", periods)


def build_period_range(start_year: int, end_year: int) -> list[str]:
    """把年份区间展开成年报 period_end 日期列表（YYYY-12-31）。

    供 compute 路径（CAGR/连续增长）展开"近3年""2021-2023"用。
    返回列表而非 SQL 片段——调用方再喂给 assemble(periods=...) 走 IN 占位符，
    避免 BETWEEN 误匹配季度数据。
    """
    if start_year > end_year:
        start_year, end_year = end_year, start_year
    return [f"{y}-12-31" for y in range(start_year, end_year + 1)]


def build_value_filter(
    op: str, num: float, unit: str, currency: str = "CNY"
) -> Optional[tuple[str, tuple[float, ...]]]:
    """单位感知数值过滤：先把阈值归一到元，再与 value_numeric 比较。

    返回 None 表示无法归一（非 CNY 或未知单位），调用方应放弃该 filter。

    生成: `value_numeric {op} ? AND currency = 'CNY'`
    """
    if op not in _SUPPORTED_OPS:
        return None
    normalized = normalize_to_base_unit(str(num), unit, currency)
    if normalized is None:
        return None
    return f"value_numeric {op} ? AND currency = 'CNY'", (normalized,)


def build_statement_priority_window() -> str:
    """窗口函数：每 (company_code, period_end, metric_name) 取合并口径唯一行。

    返回 ROW_NUMBER() OVER (...) AS rn 片段，外层用 WHERE rn = 1 取唯一行。
    PARTITION BY 必须含 metric_name：否则同公司同期的不同指标会被去重成一条。
    修正主 T2S 方案多公司示例丢 statement_type 优先级、可能混入 parent_only 的 bug。
    """
    return (
        "ROW_NUMBER() OVER ("
        f"PARTITION BY company_code, period_end, metric_name "
        f"ORDER BY {_STMT_PRIORITY_CASE}) AS rn"
    )


def build_ranking(limit: int, desc: bool = True) -> str:
    """ORDER BY value_numeric DESC/ASC LIMIT n。limit 经 int() 强转防注入。"""
    safe_limit = max(0, int(limit))
    direction = "DESC" if desc else "ASC"
    return f"ORDER BY value_numeric {direction} LIMIT {safe_limit}"


class AssemblerError(Exception):
    """Assembler 无法表达该查询（即席长尾），应转 T2S escape。"""


def assemble(
    *,
    companies: list[str] | None,
    metrics: list[str],
    periods: list[str],
    filters: Optional[list[dict]] = None,
    ranking: Optional[dict] = None,
) -> tuple[str, tuple[object, ...]]:
    """确定性拼装参数化 SQL，返回 (sql, params)。

    Args:
        companies: company_code 列表（如 ["300750","000651"]）。
            None 表示全公司（不拼 company 过滤）——供 compute 路径"所有公司平均值"用。
            空列表 [] 视为调用方 bug，抛 AssemblerError。
        metrics: metric_name（英文 key）列表（如 ["net_profit"]），非空。
        periods: period_end 日期列表（如 ["2024-12-31"]），可为空（不拼 period 过滤，返回多期）。
        filters: 可选，数值过滤列表，每项 {"metric": str, "op": str, "value": num, "unit": str}。
            目前 op 支持 >/<,/>=/<=/=/!=；metric 字段在 Phase 1 不参与 SQL 拼装
            （多指标各自过滤需 INTERSECT，留 Phase 2），仅做单指标阈值过滤。
        ranking: 可选，{"limit": int, "by_metric": str, "desc": bool}。

    Returns:
        (sql, params)。sql 形如:
            SELECT * FROM (
              SELECT *, ROW_NUMBER() OVER (...) AS rn
              FROM metric_records WHERE ... AND source_section IN (...)
            ) WHERE rn = 1 [ORDER BY value_numeric DESC LIMIT n]

    Raises:
        AssemblerError: companies 为空列表，metrics 为空，或 filter 含不支持的 op/单位。
    """
    if companies is not None and not companies:
        raise AssemblerError("companies 为空列表（用 None 表示全公司）")
    if not metrics:
        raise AssemblerError("metrics 列表为空")

    clauses: list[str] = []
    params: list[object] = []

    if companies is not None:
        c_sql, c_params = build_company_filter(companies)
        clauses.append(c_sql)
        params.extend(c_params)

    m_sql, m_params = build_metric_filter(metrics)
    clauses.append(m_sql)
    params.extend(m_params)

    if periods:
        p_sql, p_params = build_period_filter(periods)
        clauses.append(p_sql)
        params.extend(p_params)

    for f in filters or []:
        op = str(f.get("op", ""))
        try:
            value = float(f.get("value"))
        except (TypeError, ValueError):
            raise AssemblerError(f"filter value 非数值: {f.get('value')}")
        unit = str(f.get("unit", "元"))
        vf = build_value_filter(op, value, unit)
        if vf is None:
            raise AssemblerError(f"无法归一 filter: op={op} unit={unit}")
        vf_sql, vf_params = vf
        clauses.append(vf_sql)
        params.extend(vf_params)

    clauses.append(_SECTION_WHITELIST)

    window = build_statement_priority_window()
    inner = (
        f"SELECT *, {window} FROM metric_records "
        f"WHERE {' AND '.join(clauses)}"
    )
    sql = f"SELECT * FROM ({inner}) WHERE rn = 1"

    if ranking:
        limit = int(ranking.get("limit", 10))
        desc = bool(ranking.get("desc", True))
        # 指定了具体公司列表时不限制返回行数（用户要对比所有指定公司），
        # 只用 ORDER BY 排序。LIMIT 仅在全公司排名（companies 为 None）时生效。
        if companies is not None:
            direction = "DESC" if desc else "ASC"
            sql += f" ORDER BY value_numeric {direction}"
        else:
            sql += " " + build_ranking(limit, desc)

    return sql, tuple(params)
