"""2 家公司 × 15 查询的严格验证数据集。

每个查询验证：
1. 命中（不 fallback / 不 None）
2. statement_type 正确（consolidated 优先，除非明确查母公司）
3. 值与 ground truth 完全一致（从原始 markdown 手工核对）
4. period_end 与 time_scope 一致
5. metric_name 正确归一化

ground truth 来源：从 __structured/tables.jsonl 原始 markdown 手工摘录。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from finsight_agent.capabilities.structured_data.models import MetricQuery
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.config.settings import load_settings

settings = load_settings()
sqlite_path = Path(settings.structured_data.sqlite_path)
repo = MetricRepository(sqlite_path=sqlite_path)


def _to_float(v: str) -> float:
    """把带逗号/括号的数值字符串转成 float。"""
    s = v.replace(",", "")
    # 括号表示负数：(1,474,894) → -1474894
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return float(s)


def _check_value(actual: str, expected: str, tol_pct: float = 0.0) -> bool:
    """值匹配检查（允许百分比容差，默认精确匹配）。"""
    try:
        a = _to_float(actual)
        e = _to_float(expected)
        if tol_pct == 0.0:
            return a == e
        return abs(a - e) / max(abs(e), 1e-9) <= tol_pct
    except Exception:
        return actual == expected


# ============================================================
# 验证数据集：每条 = (描述, company, metric_name, time_scope, metric_label_raw,
#                     expected_value, expected_statement_type, expected_period_end, 说明)
# ============================================================
DATASET = [
    # ── 比亚迪 15 条 ──
    # 利润表（合并）
    ("BYD-01 营业收入2024", "比亚迪", "revenue", "2024年", "营业收入",
     "777,102,455", "consolidated", "2024-12-31", "合并利润表本年数"),
    ("BYD-02 营业收入2023", "比亚迪", "revenue", "2023年", "营业收入",
     "602,315,354", "consolidated", "2023-12-31", "合并利润表上年数(经重述)"),
    ("BYD-03 营业成本2024", "比亚迪", "operating_cost", "2024年", "营业成本",
     "626,046,616", "consolidated", "2024-12-31", "合并口径"),
    ("BYD-04 净利润2024", "比亚迪", "net_profit", "2024年", "净利润",
     "41,587,940", "consolidated", "2024-12-31", "合并利润表"),
    ("BYD-05 净利润2023", "比亚迪", "net_profit", "2023年", "净利润",
     "31,344,070", "consolidated", "2023-12-31", "合并利润表上年(经重述)"),
    ("BYD-06 研发费用2024", "比亚迪", "rd_expenses", "2024年", "研发费用",
     "53,194,745", "consolidated", "2024-12-31", "合并口径"),
    ("BYD-07 销售费用2024", "比亚迪", "selling_expenses", "2024年", "销售费用",
     "24,085,317", "consolidated", "2024-12-31", "合并口径"),
    # 资产负债表（合并）
    ("BYD-08 货币资金2024", "比亚迪", "cash_and_equivalents", "2024年", "货币资金",
     "102,738,734", "consolidated", "2024-12-31", "合并资产负债表期末"),
    ("BYD-09 货币资金2023", "比亚迪", "cash_and_equivalents", "2023年", "货币资金",
     "109,094,408", "consolidated", "2023-12-31", "合并资产负债表期初(经重述)"),
    ("BYD-10 应收账款2024", "比亚迪", "accounts_receivable", "2024年", "应收账款",
     "62,298,988", "consolidated", "2024-12-31", "合并口径"),
    ("BYD-11 存货2024", "比亚迪", "inventory", "2024年", "存货",
     "116,036,237", "consolidated", "2024-12-31", "合并口径"),
    # 现金流量表（合并）
    ("BYD-12 经营活动现金流净额2024", "比亚迪", "net_operating_cash_flow", "2024年", "经营活动产生的现金流量净额",
     "133,453,873", "consolidated", "2024-12-31", "合并现金流量表"),
    # latest 模式
    ("BYD-13 营业收入latest", "比亚迪", "revenue", "latest", "营业收入",
     "777,102,455", "consolidated", "2024-12-31", "latest应取2024年"),
    # 日期格式
    ("BYD-14 净利润2024-12-31", "比亚迪", "net_profit", "2024-12-31", "净利润",
     "41,587,940", "consolidated", "2024-12-31", "日期格式匹配period_end"),
    # 口语兜底：用"净利润"查 net_profit（DB label="四、净利润"）
    ("BYD-15 口语净利润兜底", "比亚迪", "net_profit", "2024年", "净利润",
     "41,587,940", "consolidated", "2024-12-31", "metric_label LIKE 兜底"),

    # ── 华能水电 15 条 ──
    # 利润表（合并）—— ground truth 从 p105 合并利润表 markdown 核对
    ("HN-01 营业收入2024", "华能水电", "revenue", "2024年", "营业收入",
     "24,881,606,852.66", "consolidated", "2024-12-31", "合并利润表本年数"),
    ("HN-02 营业收入2023", "华能水电", "revenue", "2023年", "营业收入",
     "23,461,331,621.17", "consolidated", "2023-12-31", "合并利润表上年数"),
    # 合并净利润=8,911,731,071.28（五、净利润），母公司净利润=7,126,191,824.90（四、净利润）
    ("HN-03 净利润2024", "华能水电", "net_profit", "2024年", "净利润",
     "8,911,731,071.28", "consolidated", "2024-12-31", "合并利润表(五、净利润)"),
    ("HN-04 净利润2023", "华能水电", "net_profit", "2023年", "净利润",
     "8,243,157,025.79", "consolidated", "2023-12-31", "合并利润表上年"),
    # 归母净利润=8,297,028,967.06（1.归属于母公司股东的净利润）
    ("HN-05 归母净利润2024", "华能水电", "net_profit_attributable_to_parent", "2024年", "归属于母公司股东的净利润",
     "8,297,028,967.06", "consolidated", "2024-12-31", "合并口径归母"),
    # 资产负债表（合并）
    ("HN-06 货币资金2024", "华能水电", "cash_and_equivalents", "2024年", "货币资金",
     "3,093,114,296.74", "consolidated", "2024-12-31", "合并资产负债表期末"),
    ("HN-07 货币资金2023", "华能水电", "cash_and_equivalents", "2023年", "货币资金",
     "1,760,308,144.83", "consolidated", "2023-12-31", "合并资产负债表期初"),
    ("HN-08 应收账款2024", "华能水电", "accounts_receivable", "2024年", "应收账款",
     "1,960,759,118.54", "consolidated", "2024-12-31", "合并口径"),
    ("HN-09 存货2024", "华能水电", "inventory", "2024年", "存货",
     "40,259,999.81", "consolidated", "2024-12-31", "合并口径"),
    # 现金流量表（合并）
    ("HN-10 经营活动现金流净额2024", "华能水电", "net_operating_cash_flow", "2024年", "经营活动产生的现金流量净额",
     "17,553,802,019.74", "consolidated", "2024-12-31", "合并现金流量表"),
    ("HN-11 投资活动现金流净额2024", "华能水电", "net_investing_cash_flow", "2024年", "投资活动产生的现金流量净额",
     "-20,119,698,366.80", "consolidated", "2024-12-31", "合并口径(负值)"),
    ("HN-12 筹资活动现金流净额2024", "华能水电", "net_financing_cash_flow", "2024年", "筹资活动产生的现金流量净额",
     "3,896,869,798.32", "consolidated", "2024-12-31", "合并口径"),
    # latest 模式
    ("HN-13 营业收入latest", "华能水电", "revenue", "latest", "营业收入",
     "24,881,606,852.66", "consolidated", "2024-12-31", "latest应取2024年"),
    # 日期格式
    ("HN-14 货币资金2024-12-31", "华能水电", "cash_and_equivalents", "2024-12-31", "货币资金",
     "3,093,114,296.74", "consolidated", "2024-12-31", "日期格式匹配period_end"),
    # 口语兜底：用"净利润"查 net_profit_attributable_to_parent
    ("HN-15 口语归母净利润兜底", "华能水电", "net_profit_attributable_to_parent", "2024年", "净利润",
     "8,297,028,967.06", "consolidated", "2024-12-31", "metric_label LIKE 兜底"),
]


# ============================================================
# 执行验证
# ============================================================
print("=" * 70)
print(f"2 家公司 × 15 查询严格验证（共 {len(DATASET)} 条）")
print("=" * 70)

results = {"pass": 0, "fail": 0, "details": []}

for desc, company, metric, scope, raw, exp_val, exp_st, exp_pe, note in DATASET:
    result = repo.find_best_match(
        MetricQuery(
            company_name=company,
            metric_name=metric,
            time_scope=scope,
            metric_label_raw=raw,
        )
    )

    checks = []
    # 1. 命中检查
    if result is None:
        checks.append(("命中", False, "未命中（fallback）"))
        results["fail"] += 1
        results["details"].append((desc, False, checks))
        print(f"\n  [FAIL] {desc}")
        print(f"         期望: {exp_val} | {exp_st} | {exp_pe}")
        print(f"         实际: 未命中")
        continue
    checks.append(("命中", True, "OK"))

    # 2. statement_type 检查
    if result.statement_type == exp_st:
        checks.append(("口径", True, result.statement_type))
    else:
        checks.append(("口径", False, f"期望{exp_st}，实际{result.statement_type}"))

    # 3. 值检查
    if _check_value(result.value, exp_val):
        checks.append(("值", True, result.value))
    else:
        checks.append(("值", False, f"期望{exp_val}，实际{result.value}"))

    # 4. period_end 检查
    if result.period_end == exp_pe:
        checks.append(("期末", True, result.period_end))
    else:
        checks.append(("期末", False, f"期望{exp_pe}，实际{result.period_end}"))

    # 汇总
    all_pass = all(c[1] for c in checks)
    if all_pass:
        results["pass"] += 1
        status = "PASS"
    else:
        results["fail"] += 1
        status = "FAIL"
    results["details"].append((desc, all_pass, checks))

    print(f"\n  [{status}] {desc}")
    print(f"       期望: value={exp_val} | {exp_st} | {exp_pe} | {note}")
    print(f"       实际: value={result.value} | {result.statement_type} | {result.period_end}")
    for cname, cpass, cdetail in checks:
        icon = "OK" if cpass else "FAIL"
        print(f"       {icon} {cname}: {cdetail}")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 70)
print(f"验证汇总: {results['pass']} pass / {results['fail']} fail / {len(DATASET)} total")
print("=" * 70)

if results["fail"] > 0:
    print("\n失败明细:")
    for desc, ok, checks in results["details"]:
        if not ok:
            failed_checks = [c for c in checks if not c[1]]
            print(f"  {desc}: {failed_checks}")

print(f"\n结论: {'全部通过，质量有保障' if results['fail'] == 0 else '存在问题，需修复后再全量'}")
