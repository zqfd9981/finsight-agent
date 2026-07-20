"""路径② 计算注册表：取数（Assembler 返回 list[MetricRecord]）+ Python 计算。

确定性计算，无 LLM。解决 Assembler 构造不出但可确定性表达的查询：
聚合（avg/sum/max/min/count）、增长（yoy/qoq/cagr）、连续增长。

设计要点：
- 输入是 list[MetricRecord]（Assembler/execute_parameterized_sql 的产物），已是行形状。
- 输出是 list[dict]（ [{"label","value","unit"}, ...] ），供 ComputedResult.rows 承载。
- 每个函数处理空列表/缺数值的健壮性：数据不足返回空列表，由 service 判定降级。
- 增长类（yoy/cagr/consecutive）按 period_end 升序排序后取首公司序列。
- **单位归一**：DB 中同一指标可能存"元"/"千元"/"万元"/"百万元"/"亿元"多种单位，
  聚合/增长计算前必须用 normalize_to_base_unit 归一到元，否则会得到错误结果
  （如"千元"和"亿元"直接相加）。

不在本模块：
- 跨公司比率排行（毛利率排行）需双原料 + 衍生公式 + 排序，属 service 编排，非单指标计算。
- 多指标复合谓词（净利润>100亿且营收>1000亿）走 Python 集合交集，见 service。
"""
from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from .unit_normalizer import normalize_to_base_unit

if TYPE_CHECKING:
    from .models import ComputePlan, MetricRecord


def _to_float(value: str) -> float | None:
    """把 MetricRecord.value（字符串）转 float。千分位逗号 + 括号负值兼容。"""
    if not value or not isinstance(value, str):
        return None
    s = value.strip().replace(",", "")
    if not s or s in ("-", "—", "N/A", "n/a"):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _numeric_rows(rows: list["MetricRecord"]) -> list[tuple["MetricRecord", float]]:
    """过滤出 value 可转 float 且单位可归一到元的行，返回 (record, 归一后元值) 列表。

    关键：用 normalize_to_base_unit 把 (value, unit) 归一到元，避免"千元"和"亿元"
    直接相加导致的量级错误（M-710 聚合单位错误的根因）。
    """
    out: list[tuple["MetricRecord", float]] = []
    for r in rows:
        base = normalize_to_base_unit(r.value, r.unit, r.currency or "CNY")
        if base is not None:
            out.append((r, base))
            continue
        # 单位不可归一（如 % / 空）→ 退回原始 value 转 float
        v = _to_float(r.value)
        if v is not None:
            out.append((r, v))
    return out


def _first_unit(rows: list["MetricRecord"]) -> str:
    """聚合结果的展示单位。归一到元后统一用"元"，由 format_display_value 换算到亿元。"""
    for r in rows:
        if r.unit:
            return "元"  # 强制元，因为 _numeric_rows 已归一到元
    return ""


def compute_avg(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    nums = _numeric_rows(rows)
    if not nums:
        return []
    val = statistics.mean(n for _, n in nums)
    return [{"label": f"{plan.metric_raw}平均值", "value": round(val, 2), "unit": _first_unit(rows)}]


def compute_sum(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    nums = _numeric_rows(rows)
    if not nums:
        return []
    val = sum(n for _, n in nums)
    return [{"label": f"{plan.metric_raw}合计", "value": round(val, 2), "unit": _first_unit(rows)}]


def compute_max(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    nums = _numeric_rows(rows)
    if not nums:
        return []
    rec, val = max(nums, key=lambda x: x[1])
    label = f"{plan.metric_raw}最高值（{rec.company_name}）"
    return [{"label": label, "value": round(val, 2), "unit": rec.unit}]


def compute_min(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    nums = _numeric_rows(rows)
    if not nums:
        return []
    rec, val = min(nums, key=lambda x: x[1])
    label = f"{plan.metric_raw}最低值（{rec.company_name}）"
    return [{"label": label, "value": round(val, 2), "unit": rec.unit}]


def compute_count(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    return [{"label": f"{plan.metric_raw}记录数", "value": len(rows), "unit": "条"}]


def _sorted_series(rows: list["MetricRecord"]) -> list[tuple["MetricRecord", float]]:
    """取首公司、按 period_end 升序的 (record, num) 序列。数据不足返回空。"""
    if not rows:
        return []
    first_company = rows[0].company_code
    series = [(r, n) for r, n in _numeric_rows(rows) if r.company_code == first_company]
    series.sort(key=lambda x: x[0].period_end)
    return series


def compute_yoy(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    """同比增长率：(最新期 - 上一期) / 上一期 * 100。需至少 2 期。"""
    series = _sorted_series(rows)
    if len(series) < 2:
        return []
    prev_val = series[-2][1]
    curr_val = series[-1][1]
    if prev_val == 0:
        return []
    rate = (curr_val - prev_val) / abs(prev_val) * 100
    label = f"{plan.metric_raw}同比增长率"
    return [{"label": label, "value": round(rate, 2), "unit": "%"}]


def compute_qoq(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    """环比增长率：与 yoy 同算法（取最近两期），区别在期次间距由调用方决定。"""
    return compute_yoy(rows, plan)


def compute_cagr(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    """复合增长率：(末值/首值)^(1/年数) - 1 * 100。需 years+1 期。"""
    series = _sorted_series(rows)
    years = plan.years if plan.years > 0 else (len(series) - 1)
    if years <= 0 or len(series) < years + 1:
        return []
    first_val = series[0][1]
    last_val = series[-1][1]
    if first_val <= 0 or last_val <= 0:
        return []
    rate = (last_val / first_val) ** (1.0 / years) - 1
    label = f"{plan.metric_raw}{years}年复合增长率"
    return [{"label": label, "value": round(rate * 100, 2), "unit": "%"}]


def compute_consecutive_growth(rows: list["MetricRecord"], plan: "ComputePlan") -> list[dict]:
    """连续 N 年增长判定：最近 N 期每期都较上期增长。需 N+1 期。

    当 plan.years=0 时（query 为"连续增长几年了"无具体 N）：
    计算最长连续增长期数（从最近一期往前回溯，直到首次下降），
    label 改为"已连续增长N年"，value 为期数。
    """
    series = _sorted_series(rows)
    if len(series) < 2:
        return []

    # 模式 A：plan.years > 0，判定最近 N 年是否全部增长
    if plan.years > 0:
        n = plan.years
        if len(series) < n + 1:
            return []
        tail = series[-(n + 1):]  # n+1 个点 → n 个相邻差
        grew_all = all(tail[i + 1][1] > tail[i][1] for i in range(n))
        detail = "、".join(
            f"{r.period_end[:4]}年{('增长' if tail[i + 1][1] > tail[i][1] else '下降')}"
            for i, (r, _) in enumerate(tail[:-1])
        )
        label = f"连续{n}年{plan.metric_raw}增长"
        return [{"label": label, "value": "是" if grew_all else "否", "unit": "", "detail": detail}]

    # 模式 B：plan.years = 0，问"已连续增长几年"，计算最长连续增长期数
    # 从最近一期往前回溯，统计连续增长期数
    n = 0
    for i in range(len(series) - 1, 0, -1):
        if series[i][1] > series[i - 1][1]:
            n += 1
        else:
            break
    # 生成详情：从最长连续增长起点到最近一期
    start_idx = len(series) - n - 1
    tail = series[start_idx:] if n > 0 else series[-2:]
    detail = "、".join(
        f"{r.period_end[:4]}年{('增长' if tail[i + 1][1] > tail[i][1] else '下降')}"
        for i, (r, _) in enumerate(tail[:-1])
    )
    label = f"{plan.metric_raw}已连续增长{n}年"
    return [{"label": label, "value": str(n), "unit": "年", "detail": detail}]


# 操作分发表：op → (计算函数, ComputedResult.kind)
COMPUTE_OPS: dict[str, tuple[object, str]] = {
    "avg": (compute_avg, "aggregate"),
    "sum": (compute_sum, "aggregate"),
    "max": (compute_max, "aggregate"),
    "min": (compute_min, "aggregate"),
    "count": (compute_count, "aggregate"),
    "yoy": (compute_yoy, "growth"),
    "qoq": (compute_qoq, "growth"),
    "cagr": (compute_cagr, "growth"),
    "consecutive_growth": (compute_consecutive_growth, "consecutive"),
}


def compute(op: str, rows: list["MetricRecord"], plan: "ComputePlan") -> tuple[str, list[dict]]:
    """按 op 分发计算。返回 (kind, rows)。未知 op 或数据不足返回 ("", [])。"""
    entry = COMPUTE_OPS.get(op)
    if entry is None:
        return "", []
    fn, kind = entry
    return kind, fn(rows, plan)
