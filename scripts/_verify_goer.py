"""歌尔股份 (002241) 30 个查询验证：注释表占 40%。

验证重点：
1. 三表数据正确性（资产负债表/利润表/现金流量表）
2. 注释区数据入库（修复2验证）
3. 跨年度对比 + 母公司报表
4. 注释区 source_caption 匹配（注释表有标题，用 caption 精确匹配）
"""
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "var/data/structured_data/metrics.db"
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

passed = 0
failed = 0
results = []


def check(qid: str, description: str, where_clause: str, expected_min: int = 1,
          expected_value: str | None = None):
    """执行查询并验证结果。"""
    global passed, failed
    cur.execute(f"SELECT * FROM metric_records WHERE {where_clause} LIMIT 5")
    rows = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM metric_records WHERE {where_clause}")
    total = cur.fetchone()[0]

    ok = False
    detail = ""
    if expected_value is not None:
        if rows and rows[0]["value"] == expected_value:
            ok = True
            detail = f"value={rows[0]['value']}"
        else:
            ok = False
            detail = f"expected={expected_value}, got={rows[0]['value'] if rows else 'NULL'}"
    else:
        if total >= expected_min:
            ok = True
            detail = f"{total} 条" + (f", 首条={rows[0]['value']}" if rows else "")
        else:
            ok = False
            detail = f"expected>={expected_min}, got={total}"

    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    results.append((qid, status, description[:40], detail))
    print(f"  {qid} [{status}] {description[:50]}  {detail}")


print("=" * 90)
print("歌尔股份 (002241) — 30 个查询验证（注释表占 40%）")
print("=" * 90)

# ============================================================
# Q01-Q08: 三表-资产负债表（8个）
# ============================================================
check("Q01", "资产负债表-货币资金(合并期末余额)",
      "company_code='002241' AND metric_label='货币资金' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="17466492869.05")

check("Q02", "资产负债表-应收账款(合并期末余额)",
      "company_code='002241' AND metric_label='应收账款' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="17881372031.94")

check("Q03", "资产负债表-存货(合并期末余额)",
      "company_code='002241' AND metric_label='存货' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="10478868878.63")

check("Q04", "资产负债表-资产总计(合并期末余额)",
      "company_code='002241' AND metric_label='资产总计' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="82706773086.83")

check("Q05", "资产负债表-负债合计(合并期末余额)",
      "company_code='002241' AND metric_label='负债合计' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'")

check("Q06", "资产负债表-短期借款(合并期末余额)",
      "company_code='002241' AND metric_label='短期借款' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'")

check("Q07", "资产负债表-货币资金(合并期初余额)",
      "company_code='002241' AND metric_label='货币资金' AND time_scope='期初余额' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="14737312329.71")

check("Q08", "资产负债表-应付账款(合并期末余额)",
      "company_code='002241' AND metric_label='应付账款' AND time_scope='期末余额' AND statement_type='consolidated' AND source_section='balance_sheet'")

# ============================================================
# Q09-Q13: 三表-利润表 + 现金流量表（5个）
# ============================================================
check("Q09", "利润表-营业总收入(合并2024年)",
      "company_code='002241' AND metric_label='一、营业总收入' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="100953848156.08")

check("Q10", "利润表-营业总收入(合并2023年)",
      "company_code='002241' AND metric_label='一、营业总收入' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="98573902273.14")

check("Q11", "利润表-净利润(合并2024年)",
      "company_code='002241' AND source_section='income_statement' AND statement_type='consolidated' AND metric_label LIKE '%净利润%' AND time_scope='2024年'")

check("Q12", "现金流量表-经营活动现金流量净额(合并2024年)",
      "company_code='002241' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="6200452181.84")

check("Q13", "现金流量表-经营活动现金流量净额(合并2023年)",
      "company_code='002241' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="8151888243.38")

# ============================================================
# Q14-Q25: 注释区（12个，40%）— 修复2重点验证
# ============================================================
check("Q14", "注释区-库存现金(合并)",
      "company_code='002241' AND metric_label='库存现金' AND source_section='notes' AND statement_type='consolidated'")

check("Q15", "注释区-银行存款(合并)",
      "company_code='002241' AND metric_label='银行存款' AND source_section='notes' AND statement_type='consolidated'")

check("Q16", "注释区-其他货币资金(合并)",
      "company_code='002241' AND metric_label='其他货币资金' AND source_section='notes' AND statement_type='consolidated'")

check("Q17", "注释区-货币资金 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%货币资金%' AND statement_type='consolidated'")

check("Q18", "注释区-管理费用 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%管理费用%' AND statement_type='consolidated'")

check("Q19", "注释区-销售费用 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%销售费用%' AND statement_type='consolidated'")

check("Q20", "注释区-应交税费 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%应交税费%' AND statement_type='consolidated'")

check("Q21", "注释区-递延所得税资产 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%递延所得税资产%' AND statement_type='consolidated'")

check("Q22", "注释区-其他综合收益 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%其他综合收益%' AND statement_type='consolidated'")

check("Q23", "注释区-现金流量表补充资料 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%现金流量表补充资料%' AND statement_type='consolidated'")

check("Q24", "注释区-所有权受限资产 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%所有权或使用权受到限制%' AND statement_type='consolidated'")

check("Q25", "注释区-税金及附加 source_caption",
      "company_code='002241' AND source_section='notes' AND source_caption LIKE '%税金及附加%' AND statement_type='consolidated'")

# ============================================================
# Q26-Q28: 跨年度对比（3个）
# ============================================================
check("Q26", "跨年度-资产总计 期初 vs 期末",
      "company_code='002241' AND metric_label='资产总计' AND statement_type='consolidated' AND source_section='balance_sheet' AND time_scope IN ('期初余额','期末余额')",
      expected_min=2)

check("Q27", "跨年度-营业总收入 2023 vs 2024",
      "company_code='002241' AND metric_label='一、营业总收入' AND statement_type='consolidated' AND source_section='income_statement' AND time_scope IN ('2023年','2024年')",
      expected_min=2)

check("Q28", "跨年度-经营活动现金流量净额 2023 vs 2024",
      "company_code='002241' AND metric_label='经营活动产生的现金流量净额' AND statement_type='consolidated' AND source_section='cash_flow_statement' AND time_scope IN ('2023年','2024年')",
      expected_min=2)

# ============================================================
# Q29-Q30: 母公司报表（2个）
# ============================================================
check("Q29", "母公司-资产总计(期末余额)",
      "company_code='002241' AND metric_label='资产总计' AND time_scope='期末余额' AND statement_type='parent_only' AND source_section='balance_sheet'")

check("Q30", "母公司-营业收入(2024年)",
      "company_code='002241' AND metric_label='一、营业收入' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='income_statement'",
      expected_value="24841538078.97")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 90)
print(f"验证结果: {passed}/30 通过, {failed}/30 失败")
print("=" * 90)

if failed > 0:
    print("\n失败查询:")
    for qid, status, desc, detail in results:
        if status == "FAIL":
            print(f"  {qid} {desc}  {detail}")

conn.close()
