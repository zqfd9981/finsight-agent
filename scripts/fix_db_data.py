"""一次性 DB 数据修复脚本：修复单位错误、统一 EPS 命名。

修复内容：
1. 比亚迪 2024 营收/总资产：单位"元"但数值是百万元量级 → 乘以 10000 (元 → 百万元→元)
   - 777102455 元 → 7771024550000 元（即 7771.02 亿元）
   - 783355855 元 → 7833558550000 元（即 7832 亿元）
2. 邮储银行净利润：单位"元"但数值是百万元量级 → 乘以 10000
   - 86716 元 → 867160000 元（即 8.67 亿元）—— 不对，邮储银行真实净利润 867 亿
   - 实际：邮储银行 2024 净利润 ~867 亿元，DB 存的是 86716 元
   - 86716 → 867.16 亿 = 86716000000 元，应乘以 1000000 (因为 86716 * 1000000 = 86716000000)
3. basic_eps → basic_earnings_per_share，diluted_eps → diluted_earnings_per_share
4. basic_earnings_per_share 单位 "千元"/"百万元" → "元/股"（EPS 应为元/股，且数值不变）
"""
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB = Path("var/data/structured_data/metrics.db")
BACKUP = DB.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

shutil.copy2(DB, BACKUP)
print(f"已备份 DB → {BACKUP.name}")

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# 1. 比亚迪营收/总资产：数值是"百万元"量级但单位标"元"
#    比亚迪 2024 营收真实 7771.02 亿元 = 77,710,245,50,000 元
#    DB 存 777,102,455 (元) → 应为 777,102,455 × 10000 = 7,771,024,550,000 元
#    比亚迪 2024 总资产真实 7832 亿元 = 7,832,000,000,000 元
#    DB 存 783,355,855 (元) → 应为 783,355,855 × 10000 = 7,833,558,550,000 元
#    即数值 × 10000，单位保持"元"
#    （第一条"一、营业收入"是合并报表，第二条"营业收入"是母公司，只修合并）
print("\n=== 修复比亚迪营收 ===")
cur.execute("""
    UPDATE metric_records
    SET value_numeric = value_numeric * 10000,
        value = CAST(CAST(value AS REAL) * 10000 AS TEXT)
    WHERE company_code='002594' AND metric_name='revenue'
      AND metric_label LIKE '一、营业收入%' AND period_end='2024-12-31'
""")
print(f"  受影响行数: {cur.rowcount}")
cur.execute("""
    UPDATE metric_records
    SET value_numeric = value_numeric * 10000,
        value = CAST(CAST(value AS REAL) * 10000 AS TEXT)
    WHERE company_code='002594' AND metric_name='revenue'
      AND metric_label LIKE '一、营业收入%' AND period_end='2023-12-31'
""")
print(f"  2023 受影响行数: {cur.rowcount}")

print("=== 修复比亚迪总资产 ===")
cur.execute("""
    UPDATE metric_records
    SET value_numeric = value_numeric * 10000,
        value = CAST(CAST(value AS REAL) * 10000 AS TEXT)
    WHERE company_code='002594' AND metric_name='total_assets'
      AND period_end='2024-12-31'
""")
print(f"  受影响行数: {cur.rowcount}")

# 2. 邮储银行净利润：DB 存 86716 (元)，真实 867 亿元
#    867 亿元 = 86,716,000,000 元，DB 存 86716 → 需 × 1000000
print("=== 修复邮储银行净利润 ===")
cur.execute("""
    UPDATE metric_records
    SET value_numeric = value_numeric * 1000000,
        value = CAST(CAST(value AS REAL) * 1000000 AS TEXT)
    WHERE company_name LIKE '%邮储%' AND metric_name='net_profit'
""")
print(f"  受影响行数: {cur.rowcount}")

# 3. 统一 EPS 命名：basic_eps → basic_earnings_per_share
print("=== 统一 EPS 命名 ===")
cur.execute("UPDATE metric_records SET metric_name='basic_earnings_per_share' WHERE metric_name='basic_eps'")
print(f"  basic_eps → basic_earnings_per_share: {cur.rowcount} 行")
cur.execute("UPDATE metric_records SET metric_name='diluted_earnings_per_share' WHERE metric_name='diluted_eps'")
print(f"  diluted_eps → diluted_earnings_per_share: {cur.rowcount} 行")

# 4. EPS 单位修复：EPS 应为"元/股"，不是"千元"/"百万元"
#    数值保持不变（如 11.58 元/股），只改 unit 字段
print("=== 修复 EPS 单位 ===")
cur.execute("""
    UPDATE metric_records
    SET unit='元/股'
    WHERE metric_name IN ('basic_earnings_per_share', 'diluted_earnings_per_share')
      AND unit IN ('千元', '百万元', '元')
""")
print(f"  受影响行数: {cur.rowcount}")

conn.commit()

# 验证
print("\n=== 验证修复结果 ===")
cur.execute("SELECT company_code, period_end, metric_label, metric_name, value, unit, value_numeric FROM metric_records WHERE company_code='002594' AND metric_name='revenue' AND period_end='2024-12-31'")
for r in cur.fetchall():
    print(f"  比亚迪 2024 营收: {r}")
cur.execute("SELECT company_code, period_end, metric_label, metric_name, value, unit, value_numeric FROM metric_records WHERE company_code='002594' AND metric_name='total_assets' AND period_end='2024-12-31'")
for r in cur.fetchall():
    print(f"  比亚迪 2024 总资产: {r}")
cur.execute("SELECT company_code, company_name, period_end, metric_label, metric_name, value, unit, value_numeric FROM metric_records WHERE company_name LIKE '%邮储%' AND metric_name='net_profit'")
for r in cur.fetchall():
    print(f"  邮储银行净利润: {r}")
cur.execute("SELECT company_code, period_end, metric_label, metric_name, value, unit FROM metric_records WHERE company_code='300750' AND metric_name='basic_earnings_per_share'")
for r in cur.fetchall():
    print(f"  宁德时代 EPS: {r}")
cur.execute("SELECT DISTINCT metric_name FROM metric_records WHERE metric_name LIKE '%eps%' OR metric_name LIKE '%earnings_per_share%'")
print(f"  EPS keys: {[r[0] for r in cur.fetchall()]}")

conn.close()
print("\n✅ DB 修复完成")
