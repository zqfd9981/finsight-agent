"""2 家公司 × 15 查询的广度验证数据集（共 30 条）。

覆盖各张表的各类指标：
- 资产负债表：流动资产(货币资金/应收账款/存货) + 非流动资产(固定资产/无形资产) + 资产总计
              + 流动负债(短期借款/应付账款) + 非流动负债(长期借款) + 负债合计 + 所有者权益
- 利润表：营业收入 + 营业利润 + 利润总额 + 所得税费用 + 净利润
- 现金流量表：销售商品收到的现金 + 经营/投资/筹资活动现金流净额

ground truth 来源：从 __structured/tables.jsonl 原始 markdown 手工核对。
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
    s = v.replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return float(s)


def _check_value(actual: str, expected: str) -> bool:
    try:
        return _to_float(actual) == _to_float(expected)
    except Exception:
        return actual == expected


# ============================================================
# 验证数据集：每条 = (描述, company, metric_name, time_scope, metric_label_raw,
#                     expected_value, expected_statement_type, expected_period_end, 说明)
# 所有期望值均从原始 markdown 手工核对，均为合并口径 2024 年数据
# ============================================================
DATASET = [
    # ── 比亚迪 15 条（合并口径）──
    # 资产负债表-资产端（p142）
    ("BYD-01 货币资金", "比亚迪", "cash_and_equivalents", "2024年", "货币资金",
     "102,738,734", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("BYD-02 应收账款", "比亚迪", "accounts_receivable", "2024年", "应收账款",
     "62,298,988", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("BYD-03 存货", "比亚迪", "inventory", "2024年", "存货",
     "116,036,237", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("BYD-04 固定资产", "比亚迪", "fixed_assets", "2024年", "固定资产",
     "262,287,302", "consolidated", "2024-12-31", "资产负债表非流动资产"),
    ("BYD-05 资产总计", "比亚迪", "total_assets", "2024年", "资产总计",
     "783,355,855", "consolidated", "2024-12-31", "资产负债表资产总计"),
    # 资产负债表-负债权益端（p143）
    ("BYD-06 短期借款", "比亚迪", "short_term_borrowings", "2024年", "短期借款",
     "12,103,272", "consolidated", "2024-12-31", "资产负债表流动负债"),
    ("BYD-07 应付账款", "比亚迪", "accounts_payable", "2024年", "应付账款",
     "241,643,424", "consolidated", "2024-12-31", "资产负债表流动负债"),
    ("BYD-08 长期借款", "比亚迪", "long_term_borrowings", "2024年", "长期借款",
     "8,257,786", "consolidated", "2024-12-31", "资产负债表非流动负债"),
    ("BYD-09 负债合计", "比亚迪", "total_liabilities", "2024年", "负债合计",
     "584,667,646", "consolidated", "2024-12-31", "资产负债表负债合计"),
    # 利润表（p145）
    ("BYD-10 营业收入", "比亚迪", "revenue", "2024年", "营业收入",
     "777,102,455", "consolidated", "2024-12-31", "利润表收入"),
    ("BYD-11 营业利润", "比亚迪", "operating_profit", "2024年", "营业利润",
     "50,486,047", "consolidated", "2024-12-31", "利润表利润"),
    ("BYD-12 利润总额", "比亚迪", "total_profit", "2024年", "利润总额",
     "49,680,677", "consolidated", "2024-12-31", "利润表利润总额"),
    ("BYD-13 净利润", "比亚迪", "net_profit", "2024年", "净利润",
     "41,587,940", "consolidated", "2024-12-31", "利润表净利润"),
    # 现金流量表（p149）
    ("BYD-14 销售商品收到的现金", "比亚迪", "cash_received_from_sales_of_goods_and_services", "2024年", "销售商品、提供劳务收到的现金",
     "774,347,395", "consolidated", "2024-12-31", "现金流量表经营流入"),
    ("BYD-15 经营活动现金流净额", "比亚迪", "net_operating_cash_flow", "2024年", "经营活动产生的现金流量净额",
     "133,453,873", "consolidated", "2024-12-31", "现金流量表经营净额"),

    # ── 华能水电 15 条（合并口径）──
    # 资产负债表-资产端（p101）
    ("HN-01 货币资金", "华能水电", "cash_and_equivalents", "2024年", "货币资金",
     "3,093,114,296.74", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("HN-02 应收账款", "华能水电", "accounts_receivable", "2024年", "应收账款",
     "1,960,759,118.54", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("HN-03 存货", "华能水电", "inventory", "2024年", "存货",
     "40,259,999.81", "consolidated", "2024-12-31", "资产负债表流动资产"),
    ("HN-04 固定资产", "华能水电", "fixed_assets", "2024年", "固定资产",
     "151,683,716,008.48", "consolidated", "2024-12-31", "资产负债表非流动资产"),
    ("HN-05 资产总计", "华能水电", "total_assets", "2024年", "资产总计",
     "214,607,123,371.44", "consolidated", "2024-12-31", "资产负债表资产总计"),
    # 资产负债表-负债权益端（p101）
    ("HN-06 短期借款", "华能水电", "short_term_borrowings", "2024年", "短期借款",
     "14,258,641,831.25", "consolidated", "2024-12-31", "资产负债表流动负债"),
    ("HN-07 应付账款", "华能水电", "accounts_payable", "2024年", "应付账款",
     "316,737,971.46", "consolidated", "2024-12-31", "资产负债表流动负债"),
    ("HN-08 长期借款", "华能水电", "long_term_borrowings", "2024年", "长期借款",
     "89,666,337,141.27", "consolidated", "2024-12-31", "资产负债表非流动负债"),
    ("HN-09 负债合计", "华能水电", "total_liabilities", "2024年", "负债合计",
     "135,438,631,299.02", "consolidated", "2024-12-31", "资产负债表负债合计"),
    ("HN-10 所有者权益合计", "华能水电", "total_equity", "2024年", "所有者权益",
     "79,168,492,072.42", "consolidated", "2024-12-31", "资产负债表权益合计"),
    # 利润表（p105）
    ("HN-11 营业利润", "华能水电", "operating_profit", "2024年", "营业利润",
     "10,387,465,416.27", "consolidated", "2024-12-31", "利润表营业利润"),
    ("HN-12 净利润", "华能水电", "net_profit", "2024年", "净利润",
     "8,911,731,071.28", "consolidated", "2024-12-31", "利润表净利润"),
    # 现金流量表（p109）
    ("HN-13 销售商品收到的现金", "华能水电", "cash_received_from_sales_of_goods_and_services", "2024年", "销售商品、提供劳务收到的现金",
     "27,808,713,688.30", "consolidated", "2024-12-31", "现金流量表经营流入"),
    ("HN-14 投资活动现金流净额", "华能水电", "net_investing_cash_flow", "2024年", "投资活动产生的现金流量净额",
     "-20,119,698,366.80", "consolidated", "2024-12-31", "现金流量表投资净额(负值)"),
    ("HN-15 筹资活动现金流净额", "华能水电", "net_financing_cash_flow", "2024年", "筹资活动产生的现金流量净额",
     "3,896,869,798.32", "consolidated", "2024-12-31", "现金流量表筹资净额"),
]


# ============================================================
# 执行验证
# ============================================================
print("=" * 70)
print(f"2 家公司 × 15 查询广度验证（共 {len(DATASET)} 条，覆盖三表各指标）")
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
    if result is None:
        checks.append(("命中", False, "未命中（fallback）"))
        results["fail"] += 1
        results["details"].append((desc, False, checks))
        print(f"\n  [FAIL] {desc}")
        print(f"         期望: {exp_val} | {exp_st} | {exp_pe}")
        print(f"         实际: 未命中")
        continue
    checks.append(("命中", True, "OK"))

    if result.statement_type == exp_st:
        checks.append(("口径", True, result.statement_type))
    else:
        checks.append(("口径", False, f"期望{exp_st}，实际{result.statement_type}"))

    if _check_value(result.value, exp_val):
        checks.append(("值", True, result.value))
    else:
        checks.append(("值", False, f"期望{exp_val}，实际{result.value}"))

    if result.period_end == exp_pe:
        checks.append(("期末", True, result.period_end))
    else:
        checks.append(("期末", False, f"期望{exp_pe}，实际{result.period_end}"))

    all_pass = all(c[1] for c in checks)
    if all_pass:
        results["pass"] += 1
        status = "PASS"
    else:
        results["fail"] += 1
        status = "FAIL"
    results["details"].append((desc, all_pass, checks))

    print(f"\n  [{status}] {desc} ({note})")
    print(f"       期望: value={exp_val} | {exp_st} | {exp_pe}")
    print(f"       实际: value={result.value} | {result.statement_type} | {result.period_end}")
    for cname, cpass, cdetail in checks:
        if not cpass:
            print(f"       FAIL {cname}: {cdetail}")

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

# 覆盖度统计
print("\n覆盖度:")
byd_metrics = [d for d in DATASET if d[1] == "比亚迪"]
hn_metrics = [d for d in DATASET if d[1] == "华能水电"]
print(f"  比亚迪: {len(byd_metrics)} 个指标")
print(f"  华能水电: {len(hn_metrics)} 个指标")
table_types = set(d[8].split("(")[0].strip() for d in DATASET)
print(f"  覆盖表类型: {table_types}")

print(f"\n结论: {'全部通过，质量有保障' if results['fail'] == 0 else '存在问题，需修复后再全量'}")
