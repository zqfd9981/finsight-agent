"""验证 TableExtractor 修复效果：用比亚迪 + 华能水电的真实表格测试。

重点验证：
1. 列对齐：2024年值对应 time_scope='2024年'，2023年值对应 time_scope='2023年'
2. time_scope 归一化：'2024年度'/'2024 年度'/'2024年' 统一成 '2024年'
3. period_end 按列赋值：2023年列的 period_end='2023-12-31'
4. 附注列正确跳过：'项目|附注|2024年|2023年' 结构不错位
"""
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from finsight_agent.capabilities.structured_data.table_extractor import extract_metrics_by_rule

# 测试用例：4 种典型表头结构
test_cases = [
    {
        "name": "比亚迪合并利润表（附注七|2024年|2023年(经重述)）",
        "markdown": """| 附注七 | 2024年 | 2023年(经重述) |
| 一、营业收入 | 44 | 777,102,455 | 602,315,354 |
| 减:营业成本 | 44 | 626,046,616 | 490,398,945 |
| 四、净利润 | 50 | 41,587,940 | 31,344,070 |""",
        "expect": [
            ("营业收入", "2024年", "777,102,455", "2024-12-31"),
            ("营业收入", "2023年(经重述)", "602,315,354", "2023-12-31"),
            ("净利润", "2024年", "41,587,940", "2024-12-31"),
            ("净利润", "2023年(经重述)", "31,344,070", "2023-12-31"),
        ],
    },
    {
        "name": "华能水电合并利润表（项目|附注|2024 年度|2023 年度）",
        "markdown": """| 项目 | 附注 | 2024 年度 | 2023 年度 |
| 一、营业总收入 | | 24,881,606,852.66 | 23,461,331,621.17 |
| 五、净利润 | | 8,911,731,071.28 | 8,243,157,025.79 |""",
        "expect": [
            ("营业总收入", "2024年", "24,881,606,852.66", "2024-12-31"),
            ("营业总收入", "2023年", "23,461,331,621.17", "2023-12-31"),
            ("净利润", "2024年", "8,911,731,071.28", "2024-12-31"),
            ("净利润", "2023年", "8,243,157,025.79", "2023-12-31"),
        ],
    },
    {
        "name": "比亚迪利润分配表（2024 年|2023 年，无项目列）",
        "markdown": """| 2024 年 | 2023 年 |
| 年初未分配利润 | 67,123,972 | 40,943,232 |
| 本年归属于母公司股东的净利润 | 40,254,346 | 30,040,811 |""",
        "expect": [
            ("年初未分配利润", "2024年", "67,123,972", "2024-12-31"),
            ("年初未分配利润", "2023年", "40,943,232", "2023-12-31"),
            ("归属于母公司股东的净利润", "2024年", "40,254,346", "2024-12-31"),
            ("归属于母公司股东的净利润", "2023年", "30,040,811", "2023-12-31"),
        ],
    },
    {
        "name": "资产负债表（项目|附注|期末余额|期初余额）",
        "markdown": """| 项目 | 附注 | 期末余额 | 期初余额 |
| 货币资金 | 1 | 10,000,000 | 8,000,000 |
| 应收账款 | 2 | 5,000,000 | 4,000,000 |""",
        "expect": [
            ("货币资金", "期末余额", "10,000,000", None),  # period_end 用全表默认
            ("货币资金", "期初余额", "8,000,000", None),
            ("应收账款", "期末余额", "5,000,000", None),
            ("应收账款", "期初余额", "4,000,000", None),
        ],
    },
]

print("=" * 70)
print("TableExtractor 修复验证")
print("=" * 70)

total_pass = 0
total_fail = 0

for case in test_cases:
    print(f"\n--- {case['name']} ---")
    print(f"表头: {case['markdown'].split(chr(10))[0]}")

    records = extract_metrics_by_rule(
        case["markdown"],
        company_code="TEST",
        company_name="测试公司",
        source_document_id="test_doc",
        table_id="test_table",
        caption="test",
        period_end="2024-12-31",
    )

    print(f"提取到 {len(records)} 条记录:")
    for r in records:
        print(f"  {r.metric_label} | time_scope={r.time_scope!r} | period_end={r.period_end} | value={r.value}")

    # 验证期望
    for exp_metric, exp_ts, exp_val, exp_pe in case["expect"]:
        found = False
        for r in records:
            if exp_metric in r.metric_label and r.time_scope == exp_ts and r.value == exp_val:
                if exp_pe is None or r.period_end == exp_pe:
                    found = True
                    break
        if found:
            print(f"  ✅ PASS: {exp_metric} | {exp_ts} | {exp_val} | {exp_pe}")
            total_pass += 1
        else:
            print(f"  ❌ FAIL: 期望 {exp_metric} | {exp_ts} | {exp_val} | {exp_pe}")
            total_fail += 1

print(f"\n{'=' * 70}")
print(f"总计: {total_pass} pass, {total_fail} fail")
print(f"{'=' * 70}")
