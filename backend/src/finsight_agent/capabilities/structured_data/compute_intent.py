"""路径② 入口：确定性计算意图检测。

detect_compute_intent(query, entities) 扫描 query 关键词 → 产出 ComputePlan 或 None。
纯确定性，无 LLM。命中则 service 走 query_via_compute（取数 + Python 计算）；
不命中则 stage runner 回落到 Assembler 主路径。

关键词映射（保守，避免吞掉 Assembler 的 TopN 路径）：
- "复合增长"/"年均增长" → cagr
- "连续 N 年增长" → consecutive_growth
- "同比增长"/"同比" → yoy
- "环比" → qoq
- "总和"/"合计" → sum
- "平均" → avg
- "多少家"/"几家公司" → count

故意不映射 max/min："净利润最高的公司"是 TopN（Assembler ranking），"净利润最高是多少"
才是求值——歧义大，交给 Assembler + 用户措辞，不抢路由。
"""
from __future__ import annotations

import re
from typing import Optional

from .models import ComputePlan
from .sql_assembler import build_period_range

# op 关键词（顺序敏感：长尾/包含关系优先）
_KW_CAGR = ("复合增长", "年均增长")
# 连续 N 年增长（带具体数字）：连续3年增长
_KW_CONSECUTIVE = re.compile(r"连续\s*(\d+)\s*年.*?增长")
# 连续增长多久（无具体数字，问"已连续增长几年"）：连续增长几年了 / 连续增长多少年
_KW_CONSECUTIVE_QUERY = re.compile(r"连续\s*增长.*?(几年|多少年)")
_KW_YOY = ("同比增长", "同比")
_KW_QOQ = ("环比",)
# 注意："合计" 也是财务指标名"负债合计""资产合计"的组成部分，
# 用"总合计"/"求和"替代避免误匹配。用户问"总资产和负债合计"是两指标对比而非 sum。
_KW_SUM = ("总和", "总共", "总合计", "求和")
_KW_AVG = ("平均", "均值", "平均数")
_KW_COUNT = ("多少家", "几家公司", "几家")

_YEAR_RE = re.compile(r"(20\d{2})")


def detect_compute_intent(query: str, entities: dict) -> Optional[ComputePlan]:
    """扫描 query 判定是否计算类查询，命中返回 ComputePlan，否则 None。"""
    if not query:
        return None
    q = query.strip()

    op = _detect_op(q)
    if op is None:
        return None

    metric, metric_raw = _extract_metric(entities)
    if not metric:
        return None  # 没有指标，无法计算

    # 规范化：router LLM 可能把"净利润同比增长率"识别成 metric=net_profit_growth_rate
    # （即把"增长率"硬塞进 metric_name）。compute 路径需要原料指标名（net_profit），
    # 这里剥掉 _growth_rate / _yoy / _qoq / _cagr 等计算后缀。
    metric, metric_raw = _normalize_compute_metric(metric, metric_raw, op)

    companies, company_names = _extract_companies(entities)
    periods = _extract_periods(entities)
    # entities 没给 period_end 时，从 query 文本抽年份兜底
    # （router 对"2022到2024年"这种区间常输出 period_end=""）
    if not periods:
        periods = _extract_periods_from_query(q)
    years = _extract_years(q, op, periods)

    # cagr/consecutive 需要多期：若 periods 不足且有 years，按 years 展开年期
    if op in ("cagr", "consecutive_growth") and years > 0:
        periods = _ensure_period_range(periods, years)

    # yoy/qoq 至少需要 2 期：若只给 1 期，自动补上一期（上年同期）
    if op in ("yoy", "qoq"):
        periods = _ensure_yoy_periods(periods)

    return ComputePlan(
        op=op,
        metric=metric,
        metric_raw=metric_raw or metric,
        companies=companies,
        company_names=company_names,
        periods=periods,
        years=years,
    )


# 计算 op 相关的英文 token：router LLM 可能把"复合增长率/同比/环比"等
# 硬塞进 metric_name（前缀/后缀/中缀都见过）。用 token 级清洗最稳健。
# 例：net_profit_compound_growth_rate → net_profit
#     compound_growth_rate_net_profit → net_profit
#     compound_growth_rate_of_net_profit → net_profit
#     cagr_net_profit → net_profit
#     net_profit_yoy → net_profit
_COMPUTE_TOKENS: set[str] = {
    "compound", "consecutive", "growth", "rate",
    "yoy", "qoq", "cagr", "annual", "average", "avg",
    "of", "the", "for", "in", "on", "at", "to",  # 常见连接词
}

# 中文后缀关键词（用于同步清洗 metric_raw）
_COMPUTE_CN_SUFFIXES: tuple[str, ...] = (
    "同比增长率", "环比增长率", "复合增长率", "年均增长率",
    "增长率", "同比", "环比",
)

# 常见英文 metric key → 中文 label 映射（用于 follow_up 指代场景下
# router 把 metric_raw 抽成英文 key 时，转回中文避免 summary 英文泄露）。
# 与 metric_aliases.json 保持同步，只列高频指标。
_METRIC_KEY_ZH: dict[str, str] = {
    "net_profit": "净利润",
    "net_profit_attributable_to_parent": "归母净利润",
    "deducted_net_profit": "扣非净利润",
    "revenue": "营收",
    "operating_profit": "营业利润",
    "total_profit": "利润总额",
    "total_assets": "总资产",
    "total_liabilities": "负债合计",
    "total_current_assets": "流动资产",
    "total_non_current_assets": "非流动资产",
    "total_owners_equity": "所有者权益",
    "net_operating_cash_flow": "经营现金流",
    "net_investing_cash_flow": "投资现金流",
    "net_financing_cash_flow": "筹资现金流",
    "basic_earnings_per_share": "基本每股收益",
    "diluted_earnings_per_share": "稀释每股收益",
    "operating_cost": "营业成本",
    "fixed_assets": "固定资产",
    "inventory": "存货",
    "long_term_borrowings": "长期借款",
    "short_term_borrowings": "短期借款",
    "paid_in_capital": "实收资本",
    "cash_and_equivalents": "货币资金",
}


def _normalize_compute_metric(
    metric: str, metric_raw: str, op: str
) -> tuple[str, str]:
    """剥掉 router 误把"增长率/同比/环比"塞进 metric_name 的 token，还原原料指标。

    采用 token 级清洗（比前后缀剥离更稳健，能处理中缀情况如
    net_profit_compound_growth_rate）。

    例：net_profit_growth_rate → net_profit
        revenue_yoy → revenue
        net_profit_compound_growth_rate → net_profit
        compound_growth_rate_net_profit → net_profit
        cagr_net_profit → net_profit
    若 metric_raw 含中文"增长率/同比/环比"，也一并剥掉。
    """
    # 英文 metric：按 underscore 分词，剔除计算 token，重新拼接
    tokens = [t for t in metric.split("_") if t]
    cleaned_tokens = [t for t in tokens if t not in _COMPUTE_TOKENS]
    new_metric = "_".join(cleaned_tokens) if cleaned_tokens else metric

    # 同步清洗 metric_raw：去掉末尾的"增长率/同比/环比/复合增长"等中文后缀
    new_raw = metric_raw
    if metric_raw and metric_raw != metric:
        for _ in range(3):
            prev = new_raw
            for kw in _COMPUTE_CN_SUFFIXES:
                if new_raw.endswith(kw) and len(new_raw) > len(kw):
                    new_raw = new_raw[: -len(kw)].strip()
                    break
            if new_raw == prev:
                break
        # 若 raw 恰好是后缀关键词本身（如 router 把"它的同比增长率呢"里的
        # metric_raw 抽成"同比"），上面循环不会剥离（len(raw)==len(kw)），
        # 直接用会导致 label 出现"同比同比增长率"。此时回退到 standard_name。
        if new_raw in _COMPUTE_CN_SUFFIXES:
            new_raw = new_metric
    else:
        new_raw = new_metric
    # follow_up 指代场景下 router 可能把 metric_raw 抽成英文 key（如"net_profit"），
    # 直接用会导致 summary 英文泄露（如"net_profit同比增长率"）。
    # 此时用 _METRIC_KEY_ZH 映射回中文 label。
    if new_raw and new_raw in _METRIC_KEY_ZH:
        new_raw = _METRIC_KEY_ZH[new_raw]
    return new_metric, new_raw


def _detect_op(q: str) -> Optional[str]:
    # 顺序敏感：consecutive/cagr 优先于 yoy（都含"增长"）
    if _KW_CONSECUTIVE.search(q):
        return "consecutive_growth"
    # "连续增长几年了"/"连续增长多少年"——无具体 N，问的是已连续增长多少年
    if _KW_CONSECUTIVE_QUERY.search(q):
        return "consecutive_growth"
    if any(k in q for k in _KW_CAGR):
        return "cagr"
    if any(k in q for k in _KW_YOY):
        return "yoy"
    if any(k in q for k in _KW_QOQ):
        return "qoq"
    if any(k in q for k in _KW_SUM):
        return "sum"
    if any(k in q for k in _KW_AVG):
        return "avg"
    if any(k in q for k in _KW_COUNT):
        return "count"
    return None


def _extract_metric(entities: dict) -> tuple[str, str]:
    """从 entities.metric（list/dict/str）取 standard_name + raw。"""
    m = entities.get("metric", "")
    items = m if isinstance(m, list) else ([m] if isinstance(m, dict) else [])
    for it in items:
        if not isinstance(it, dict):
            continue
        std = str(it.get("standard_name") or "").strip()
        raw = str(it.get("raw") or "").strip()
        if std or raw:
            return std, raw
    # 旧格式字符串
    if isinstance(m, str) and m.strip():
        return m.strip(), m.strip()
    return "", ""


def _extract_companies(entities: dict) -> tuple[list[str], list[str]]:
    """从 entities.company 取 code 列表 + name 列表。空列表表示全公司。"""
    c = entities.get("company", "")
    items = c if isinstance(c, list) else ([c] if isinstance(c, dict) else [])
    codes: list[str] = []
    names: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = str(it.get("stock_code") or "").strip()
        name = str(it.get("standard_name") or it.get("raw") or "").strip()
        if code:
            codes.append(code)
            names.append(name or code)
    return codes, names


def _extract_periods(entities: dict) -> list[str]:
    t = entities.get("time_scope", "")
    items = t if isinstance(t, list) else ([t] if isinstance(t, dict) else [])
    periods: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        p = str(it.get("period_end") or "").strip()
        if p:
            periods.append(p)
    return periods


def _extract_periods_from_query(q: str) -> list[str]:
    """从 query 文本抽年份，生成 period_end 列表（YYYY-12-31）。

    用于 router 未输出 period_end 时的兜底（router 对"2022到2024年"这种区间
    常输出 period_end=""）。只抽显式出现的年份，区间中间年份由 _ensure_period_range
    按 years 展开。

    例："2022到2024年净利润复合增长率" → ["2022-12-31", "2024-12-31"]
        "2024年净利润同比增长率" → ["2024-12-31"]
    """
    years = sorted(set(int(m.group(1)) for m in _YEAR_RE.finditer(q)))
    return [f"{y}-12-31" for y in years]


def _extract_years(q: str, op: str, periods: list[str]) -> int:
    """从 query 抽年数（连续N年/近N年/N年复合/X到Y年区间）；cagr/consecutive 必需。"""
    if op == "consecutive_growth":
        m = _KW_CONSECUTIVE.search(q)
        if m:
            return int(m.group(1))
    m_year = re.search(r"(?:近|过去|最近)\s*(\d+)\s*年", q)
    if m_year:
        return int(m_year.group(1))
    if op == "cagr":
        m_n = re.search(r"(\d+)\s*年(?:复合|年均)", q)
        if m_n:
            return int(m_n.group(1))
        # 识别 "X到Y年" / "X-Y年" / "X至Y年" 区间，years = end - start
        m_range = re.search(r"(20\d{2})\s*[到至\-—~]\s*(20\d{2})\s*年", q)
        if m_range:
            return int(m_range.group(2)) - int(m_range.group(1))
    return 0


def _ensure_period_range(periods: list[str], years: int) -> list[str]:
    """cagr/consecutive 需 years+1 个年报点。若 periods 仅 1 个或空，按其年份回展开。"""
    if years <= 0:
        return periods
    # 取已有 periods 的最大年份作为终点
    end_year = 0
    for p in periods:
        m = _YEAR_RE.search(p)
        if m:
            y = int(m.group(1))
            if y > end_year:
                end_year = y
    if end_year == 0:
        return periods  # 无法定位终点，保持原样（compute 会因数据不足降级）
    # cagr 需 years+1 点：[end-year, end]；consecutive 同理
    return build_period_range(end_year - years, end_year)


def _ensure_yoy_periods(periods: list[str]) -> list[str]:
    """yoy/qoq 至少需要 2 期。若仅 1 期，自动补上上年同期。

    例：["2024-12-31"] → ["2023-12-31", "2024-12-31"]
        ["2024-12-31", "2023-12-31"] → 保持原样（已 2 期）
        [] → 保持空（compute 会因数据不足降级）
    """
    if len(periods) >= 2:
        return periods
    if not periods:
        return periods
    p = periods[0]
    m = _YEAR_RE.search(p)
    if not m:
        return periods
    curr_year = int(m.group(1))
    prev_period = p.replace(str(curr_year), str(curr_year - 1), 1)
    # 升序返回：上年同期在前
    return [prev_period, p]
