"""赛力斯 (601127) 30 个查询验证：注释表占 40%。

验证重点：
1. 三表数据正确性（资产负债表/利润表/现金流量表，精确值）
2. 注释区数据入库（补全注释区 p135-p193 后 notes=771，之前为 0）
3. 跨年度对比 + 母公司报表
4. 注释区 source_caption 匹配
5. 资产负债表勾稽（资产 = 负债 + 权益）
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


def check(qid: str, description: str, where_clause: str, expected_min: int = 1,
          expected_value: str | None = None):
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
    print(f"  {qid} [{status}] {description[:50]}  {detail}")


def check_recon(qid: str, description: str, sql: str, expected_diff: float = 0.01):
    global passed, failed
    cur.execute(sql)
    row = cur.fetchone()
    diff = abs(float(row[0])) if row and row[0] is not None else None
    ok = diff is not None and diff < expected_diff
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    detail = f"差额={row[0] if row else 'NULL'}"
    print(f"  {qid} [{status}] {description[:50]}  {detail}")


print("=" * 90)
print("赛力斯 (601127) — 30 个查询验证（注释表占 40%）")
print("=" * 90)

cur.execute("SELECT source_section, COUNT(*) FROM metric_records WHERE company_code='601127' GROUP BY source_section")
print("数据分布:", dict(cur.fetchall()))

# ============================================================
# Q01-Q18: 三表（18个）— 精确值验证
# ============================================================
print("\n--- 三表（18个）---")
check("Q01", "资产负债表-货币资金(合并2024期末)",
      "company_code='601127' AND metric_name='cash_and_equivalents' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="45955437989.80")

check("Q02", "资产负债表-货币资金(合并2023期末)",
      "company_code='601127' AND metric_name='cash_and_equivalents' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="13161127239.99")

check("Q03", "资产负债表-应收账款(合并2024期末)",
      "company_code='601127' AND metric_name='accounts_receivable' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="2361932209.18")

check("Q04", "资产负债表-存货(合并2024期末)",
      "company_code='601127' AND metric_name='inventory' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="2552448609.01")

check("Q05", "资产负债表-资产总计(合并2024期末)",
      "company_code='601127' AND metric_name='total_assets' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="94363958922.89")

check("Q06", "资产负债表-资产总计(合并2023期末)",
      "company_code='601127' AND metric_name='total_assets' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="51244671110.58")

check("Q07", "资产负债表-负债合计(合并2024期末)",
      "company_code='601127' AND metric_name='total_liabilities' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="82458401238.54")

check("Q08", "资产负债表-所有者权益合计(合并2024期末)",
      "company_code='601127' AND metric_name='total_equity' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="11905557684.35")

check("Q09", "利润表-营业收入(合并2024)",
      "company_code='601127' AND metric_name='revenue' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="145175822053.79")

check("Q10", "利润表-营业收入(合并2023)",
      "company_code='601127' AND metric_name='revenue' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="35841957866.81")

check("Q11", "利润表-净利润(合并2024)",
      "company_code='601127' AND metric_name='net_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="4740116433.25")

check("Q12", "利润表-净利润(合并2023)",
      "company_code='601127' AND metric_name='net_profit' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="-4156716456.96")

check("Q13", "利润表-营业利润(合并2024)",
      "company_code='601127' AND metric_name='operating_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="4942184755.17")

check("Q14", "利润表-利润总额(合并2024)",
      "company_code='601127' AND metric_name='total_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="4951347599.25")

check("Q15", "现金流量表-经营活动现金流净额(合并2024)",
      "company_code='601127' AND metric_name='net_operating_cash_flow' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="22515265144.17")

check("Q16", "现金流量表-经营活动现金流净额(合并2023)",
      "company_code='601127' AND metric_name='net_operating_cash_flow' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="6397611620.70")

check("Q17", "利润表-营业收入(母公司2024)",
      "company_code='601127' AND metric_name='revenue' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='income_statement'",
      expected_value="53112882.91")

check("Q18", "利润表-净利润(母公司2024)",
      "company_code='601127' AND metric_name='net_profit' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='income_statement'",
      expected_value="476572351.05")

# ============================================================
# Q19-Q30: 注释区（12个，40%）— source_caption 匹配验证
# ============================================================
print("\n--- 注释区（12个）---")
check("Q19", "注释区-研发费用",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%研发费用%'")

check("Q20", "注释区-销售费用",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%销售费用%'")

check("Q21", "注释区-管理费用",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%管理费用%'")

check("Q22", "注释区-应交税费",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%应交税费%'")

check("Q23", "注释区-在建工程",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%在建工程%'")

check("Q24", "注释区-所有权或使用权受限资产",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%所有权或使用权受限资产%'")

check("Q25", "注释区-现金流量表补充资料",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%现金流量表补充资料%'")

check("Q26", "注释区-资产减值损失",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%资产减值损失%'")

check("Q27", "注释区-货币资金",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%货币资金%'")

check("Q28", "注释区-存货",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%存货%'")

check("Q29", "注释区-递延收益",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%递延收益%'")

check("Q30", "注释区-固定资产",
      "company_code='601127' AND source_section='notes' AND source_caption LIKE '%固定资产%'")

# ============================================================
# 勾稽验证（额外，不计入 30 个）
# ============================================================
print("\n--- 勾稽验证 ---")
check_recon("R01", "资产总计 = 负债合计 + 所有者权益合计(合并2024)",
    """SELECT CAST(
        (SELECT CAST(value AS REAL) FROM metric_records
         WHERE company_code='601127' AND metric_name='total_assets' AND time_scope='2024年'
           AND statement_type='consolidated' AND source_section='balance_sheet')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='601127' AND metric_name='total_liabilities' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='balance_sheet')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='601127' AND metric_name='total_equity'
             AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet')
    AS REAL)""")

check_recon("R02", "净利润 = 利润总额 - 所得税费用(合并2024)",
    """SELECT CAST(
        (SELECT CAST(value AS REAL) FROM metric_records
         WHERE company_code='601127' AND metric_name='net_profit' AND time_scope='2024年'
           AND statement_type='consolidated' AND source_section='income_statement')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='601127' AND metric_name='total_profit' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='income_statement')
        + (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='601127' AND metric_name='income_tax_expense' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='income_statement')
    AS REAL)""")

print(f"\n{'=' * 90}")
print(f"验证结果: {passed} 通过, {failed} 失败 (共 {passed + failed - 2} 项查询 + 2 项勾稽)")
print(f"{'=' * 90}")
conn.close()
