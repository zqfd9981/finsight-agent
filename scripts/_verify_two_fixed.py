"""三一重工 + 海尔智家 修复后验证：30 个查询，注释表占 40%。

验证重点：
1. 三表数据正确性（资产负债表/利润表/现金流量表）
2. 注释区数据入库（修复2：注释区起点缺失兜底）
3. 海尔合并利润表/现金流量表 statement_type=consolidated（修复3：内容兜底）
4. 跨年度对比 + 母公司报表
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
          expected_value: str | None = None, company: str = ""):
    """执行查询并验证结果。"""
    global passed, failed
    sql = f"SELECT * FROM metric_records WHERE {where_clause} LIMIT 5"
    cur.execute(sql)
    rows = cur.fetchall()
    count_sql = f"SELECT COUNT(*) FROM metric_records WHERE {where_clause}"
    cur.execute(count_sql)
    total = cur.fetchone()[0]

    ok = False
    detail = ""
    if expected_value is not None:
        # 精确值验证
        if rows and rows[0]["value"] == expected_value:
            ok = True
            detail = f"value={rows[0]['value']}"
        else:
            ok = False
            detail = f"expected={expected_value}, got={rows[0]['value'] if rows else 'NULL'}"
    else:
        # 数量验证
        if total >= expected_min:
            ok = True
            detail = f"{total} 条记录" + (f", 首条={rows[0]['value']}" if rows else "")
        else:
            ok = False
            detail = f"expected>={expected_min}, got={total}"

    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    results.append((qid, company, status, description[:40], detail))
    print(f"  {qid} [{status}] {description[:50]}  {detail}")


# ============================================================
# 三一重工 (600031) — 15 个查询
# ============================================================
print("=" * 90)
print("三一重工 (600031) — 15 个查询")
print("=" * 90)

# Q01-Q04: 三表-资产负债表
check("Q01", "资产负债表-货币资金(合并2024年)",
      "company_code='600031' AND metric_label='货币资金' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="三一")

check("Q02", "资产负债表-应收账款(合并2024年)",
      "company_code='600031' AND metric_label='应收账款' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="三一")

check("Q03", "资产负债表-存货(合并2024年)",
      "company_code='600031' AND metric_label='存货' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="三一")

check("Q04", "资产负债表-资产总计(合并2024年)",
      "company_code='600031' AND metric_label='资产总计' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="152145076", company="三一")

# Q05-Q06: 三表-利润表
check("Q05", "利润表-营业总收入(合并2024年)",
      "company_code='600031' AND metric_label='一、营业总收入' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="78383379", company="三一")

check("Q06", "利润表-利润总额或净利润(合并)",
      "company_code='600031' AND source_section='income_statement' AND statement_type='consolidated' AND metric_label LIKE '%利润总额%'",
      company="三一")

# Q07: 三表-现金流量表
check("Q07", "现金流量表-经营活动现金流量净额(合并2024年)",
      "company_code='600031' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="14814278", company="三一")

# Q08-Q13: 注释区（6个，修复2验证）
check("Q08", "注释区-库存现金(合并)",
      "company_code='600031' AND metric_label='库存现金' AND source_section='notes' AND statement_type='consolidated'",
      company="三一")

check("Q09", "注释区-银行存款(合并)",
      "company_code='600031' AND metric_label='银行存款' AND source_section='notes' AND statement_type='consolidated'",
      company="三一")

check("Q10", "注释区-其他货币资金(合并)",
      "company_code='600031' AND metric_label='其他货币资金' AND source_section='notes' AND statement_type='consolidated'",
      company="三一")

check("Q11", "注释区-货币资金 source_caption 匹配",
      "company_code='600031' AND source_section='notes' AND source_caption LIKE '%货币资金%' AND statement_type='consolidated'",
      company="三一")

check("Q12", "注释区-营业收入(合并)",
      "company_code='600031' AND metric_label='营业收入' AND source_section='notes' AND statement_type='consolidated'",
      company="三一")

check("Q13", "注释区-衍生金融资产 source_caption",
      "company_code='600031' AND source_section='notes' AND source_caption LIKE '%衍生金融资产%' AND statement_type='consolidated'",
      company="三一")

# Q14: 跨年度对比
check("Q14", "跨年度-资产总计 2023 vs 2024",
      "company_code='600031' AND metric_label='资产总计' AND statement_type='consolidated' AND source_section='balance_sheet' AND time_scope IN ('2023年','2024年')",
      expected_min=2, company="三一")

# Q15: 母公司报表
check("Q15", "母公司-资产总计(2024年)",
      "company_code='600031' AND metric_label='资产总计' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='balance_sheet'",
      company="三一")


# ============================================================
# 海尔智家 (600690) — 15 个查询
# ============================================================
print("\n" + "=" * 90)
print("海尔智家 (600690) — 15 个查询")
print("=" * 90)

# Q16-Q19: 三表-资产负债表
check("Q16", "资产负债表-货币资金(合并2024年)",
      "company_code='600690' AND metric_label='货币资金' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="海尔")

check("Q17", "资产负债表-应收账款(合并2024年)",
      "company_code='600690' AND metric_label='应收账款' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="海尔")

check("Q18", "资产负债表-存货(合并2024年)",
      "company_code='600690' AND metric_label='存货' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="海尔")

check("Q19", "资产负债表-资产总计(合并2024年)",
      "company_code='600690' AND metric_label='资产总计' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      company="海尔")

# Q20: 利润表（修复3重点验证：statement_type 应为 consolidated）
check("Q20", "利润表-营业总收入(合并2024年) [修复3验证]",
      "company_code='600690' AND metric_label='一、营业总收入' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      company="海尔")

# Q21: 现金流量表（修复3重点验证：statement_type 应为 consolidated）
check("Q21", "现金流量表-经营活动现金流量净额(合并2024年) [修复3验证]",
      "company_code='600690' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      company="海尔")

# Q22-Q27: 注释区（6个，修复2验证）
check("Q22", "注释区-库存现金(合并)",
      "company_code='600690' AND metric_label='库存现金' AND source_section='notes' AND statement_type='consolidated'",
      company="海尔")

check("Q23", "注释区-银行存款(合并)",
      "company_code='600690' AND metric_label='银行存款' AND source_section='notes' AND statement_type='consolidated'",
      company="海尔")

check("Q24", "注释区-应收票据 source_caption",
      "company_code='600690' AND source_section='notes' AND source_caption LIKE '%应收票据%' AND statement_type='consolidated'",
      company="海尔")

check("Q25", "注释区-长期股权投资 source_caption",
      "company_code='600690' AND source_section='notes' AND source_caption LIKE '%长期股权投资%' AND statement_type='consolidated'",
      company="海尔")

check("Q26", "注释区-营业收入 source_caption",
      "company_code='600690' AND source_section='notes' AND source_caption LIKE '%营业收入%' AND statement_type='consolidated'",
      company="海尔")

check("Q27", "注释区-未分配利润 source_caption",
      "company_code='600690' AND source_section='notes' AND source_caption LIKE '%未分配利润%' AND statement_type='consolidated'",
      company="海尔")

# Q28: 跨年度对比
check("Q28", "跨年度-货币资金 2023 vs 2024",
      "company_code='600690' AND metric_label='货币资金' AND statement_type='consolidated' AND source_section='balance_sheet' AND time_scope IN ('2023年','2024年')",
      expected_min=2, company="海尔")

# Q29: 母公司报表
check("Q29", "母公司-资产总计(2024年)",
      "company_code='600690' AND metric_label='资产总计' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='balance_sheet'",
      company="海尔")

# Q30: 修复3验证 - 海尔利润表 consolidated 记录数
check("Q30", "修复3验证-海尔利润表 consolidated 记录数>0",
      "company_code='600690' AND source_section='income_statement' AND statement_type='consolidated'",
      expected_min=10, company="海尔")


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 90)
print(f"验证结果汇总: {passed}/30 通过, {failed}/30 失败")
print("=" * 90)

if failed > 0:
    print("\n失败查询:")
    for qid, company, status, desc, detail in results:
        if status == "FAIL":
            print(f"  {qid} [{company}] {desc}  {detail}")

conn.close()
