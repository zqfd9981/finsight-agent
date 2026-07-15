"""海天味业 (603288) 30 个查询验证：注释表占 40%。

验证重点：
1. 三表数据正确性（资产负债表/利润表/现金流量表，精确值）
2. 注释区数据入库（二次扫描修复验证，notes 之前为 0）
3. 跨年度对比 + 母公司报表
4. 注释区 source_caption 匹配
5. 资产负债表勾稽（资产 = 负债 + 权益）
6. 利润表勾稽（净利润 = 利润总额 - 所得税费用）

注意：海天味业是调味品公司（酱油），2024年业绩回升（净利润 63.6亿，同比+12.7%）。
合并利润表有"营业总收入"+"其中:营业收入"，母公司只有"营业收入"。
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
    print(f"  {qid} [{status}] {description[:50]}  {detail}")


def check_recon(qid: str, description: str, sql: str, expected_diff: float = 0.01):
    """勾稽验证：执行 SQL 返回一个数值，验证 |结果| < expected_diff。"""
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
print("海天味业 (603288) — 30 个查询验证（注释表占 40%）")
print("=" * 90)

# 数据概览
cur.execute("SELECT source_section, COUNT(*) FROM metric_records WHERE company_code='603288' GROUP BY source_section")
print("数据分布:", dict(cur.fetchall()))

# ============================================================
# Q01-Q18: 三表（18个）— 精确值验证
# ============================================================
print("\n--- 三表（18个）---")
check("Q01", "资产负债表-货币资金(合并2024期末)",
      "company_code='603288' AND metric_label='货币资金' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="22114735922.46")

check("Q02", "资产负债表-货币资金(合并2023期末)",
      "company_code='603288' AND metric_label='货币资金' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="21689385461.71")

check("Q03", "资产负债表-应收账款(合并2024期末)",
      "company_code='603288' AND metric_label='应收账款' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="242260969.75")

check("Q04", "资产负债表-存货(合并2024期末)",
      "company_code='603288' AND metric_label='存货' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="2525273760.73")

check("Q05", "资产负债表-资产总计(合并2024期末)",
      "company_code='603288' AND metric_label='资产总计' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="40858435135.91")

check("Q06", "资产负债表-资产总计(合并2023期末)",
      "company_code='603288' AND metric_label='资产总计' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="38423518405.62")

check("Q07", "资产负债表-负债合计(合并2024期末)",
      "company_code='603288' AND metric_label='负债合计' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="9456491552.41")

check("Q08", "资产负债表-短期借款(合并2024期末)",
      "company_code='603288' AND metric_label='短期借款' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet'",
      expected_value="293464953.68")

check("Q09", "利润表-营业收入(合并2024)",
      "company_code='603288' AND metric_name='revenue' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="26900977516.70")

check("Q10", "利润表-营业收入(合并2023)",
      "company_code='603288' AND metric_name='revenue' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="24559312356.59")

check("Q11", "利润表-净利润(合并2024)",
      "company_code='603288' AND metric_name='net_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="6355860951.43")

check("Q12", "利润表-净利润(合并2023)",
      "company_code='603288' AND metric_name='net_profit' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="5642186761.43")

check("Q13", "利润表-营业利润(合并2024)",
      "company_code='603288' AND metric_name='operating_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="7506580713.98")

check("Q14", "利润表-利润总额(合并2024)",
      "company_code='603288' AND metric_name='total_profit' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='income_statement'",
      expected_value="7513082344.24")

check("Q15", "现金流量表-经营活动现金流净额(合并2024)",
      "company_code='603288' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2024年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="6843710887.07")

check("Q16", "现金流量表-经营活动现金流净额(合并2023)",
      "company_code='603288' AND metric_label='经营活动产生的现金流量净额' AND time_scope='2023年' AND statement_type='consolidated' AND source_section='cash_flow_statement'",
      expected_value="7355650997.74")

check("Q17", "利润表-营业收入(母公司2024)",
      "company_code='603288' AND metric_label='一、营业收入' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='income_statement'",
      expected_value="21570815479.98")

check("Q18", "利润表-净利润(母公司2024)",
      "company_code='603288' AND metric_name='net_profit' AND time_scope='2024年' AND statement_type='parent_only' AND source_section='income_statement'",
      expected_value="3482889814.14")

# ============================================================
# Q19-Q30: 注释区（12个，40%）— source_caption LIKE 匹配验证
# ============================================================
print("\n--- 注释区（12个）---")
check("Q19", "注释区-总记录数>=50",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%'",
      expected_min=50)

check("Q20", "注释区-存货分类",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%存货分类%'",
      expected_min=16)

check("Q21", "注释区-按账龄披露",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%按账龄披露%'",
      expected_min=10)

check("Q22", "注释区-按坏账计提方法分类披露",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%按坏账计提方法分类披露%'",
      expected_min=20)

check("Q23", "注释区-存货跌价准备及合同履约成本减值准备",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%存货跌价准备及合同履约成本减值准备%'",
      expected_min=4)

check("Q24", "注释区-存货(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%存货%'",
      expected_min=20)

check("Q25", "注释区-坏账(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%坏账%'",
      expected_min=20)

check("Q26", "注释区-账龄(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%账龄%'",
      expected_min=10)

check("Q27", "注释区-跌价(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%跌价%'",
      expected_min=4)

check("Q28", "注释区-分类披露(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%分类披露%'",
      expected_min=20)

check("Q29", "注释区-合同履约成本(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%合同履约成本%'",
      expected_min=4)

check("Q30", "注释区-按坏账计提(模糊匹配)",
      "company_code='603288' AND source_section='notes' AND source_caption LIKE '%按坏账计提%'",
      expected_min=20)

# ============================================================
# 勾稽验证（额外，不计入 30 个）
# ============================================================
print("\n--- 勾稽验证 ---")
# 资产 = 负债 + 权益（合并2024）
check_recon("R01", "资产总计 = 负债合计 + 所有者权益合计(合并2024)",
    """SELECT CAST(
        (SELECT CAST(value AS REAL) FROM metric_records
         WHERE company_code='603288' AND metric_label='资产总计' AND time_scope='2024年'
           AND statement_type='consolidated' AND source_section='balance_sheet')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='603288' AND metric_label='负债合计' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='balance_sheet')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='603288' AND metric_name='total_equity'
             AND time_scope='2024年' AND statement_type='consolidated' AND source_section='balance_sheet')
    AS REAL)""")

# 净利润 = 利润总额 - 所得税费用（合并2024）
check_recon("R02", "净利润 = 利润总额 - 所得税费用(合并2024)",
    """SELECT CAST(
        (SELECT CAST(value AS REAL) FROM metric_records
         WHERE company_code='603288' AND metric_name='net_profit' AND time_scope='2024年'
           AND statement_type='consolidated' AND source_section='income_statement')
        - (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='603288' AND metric_name='total_profit' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='income_statement')
        + (SELECT CAST(value AS REAL) FROM metric_records
           WHERE company_code='603288' AND metric_name='income_tax_expense' AND time_scope='2024年'
             AND statement_type='consolidated' AND source_section='income_statement')
    AS REAL)""")

print(f"\n{'=' * 90}")
print(f"验证结果: {passed} 通过, {failed} 失败 (共 {passed + failed - 2} 项查询 + 2 项勾稽)")
print(f"{'=' * 90}")
conn.close()
