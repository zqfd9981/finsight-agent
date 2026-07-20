import sqlite3
conn = sqlite3.connect('var/data/structured_data/metrics.db')
cur = conn.cursor()
print("=== 宁德时代历年净利润 ===")
cur.execute("SELECT period_end, metric_label, metric_name, value, unit, value_numeric FROM metric_records WHERE company_code='300750' AND metric_name='net_profit' ORDER BY period_end")
for r in cur.fetchall():
    print(r)
print("\n=== 宁德时代历年营收 ===")
cur.execute("SELECT period_end, metric_label, metric_name, value, unit, value_numeric FROM metric_records WHERE company_code='300750' AND metric_name='revenue' ORDER BY period_end")
for r in cur.fetchall():
    print(r)
conn.close()
