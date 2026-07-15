"""全面测试 pandas 解析各种结构的表。

测试覆盖：
1. 三表（资产负债表/利润表/现金流量表）- 期间作列
2. 账龄表 - 账龄分桶作列
3. 变动表 - 年初/本年增加/本年减少/年末作列
4. 调节表 - 净利润调节表、所得税调节表
5. 固定资产明细 - 资产类别作列
6. 双行表头 - colspan/rowspan 合并单元格
7. 母公司报表
8. 权益变动表 - 权益科目作列（结构相反）
"""
import json
import sys
from pathlib import Path
from io import StringIO

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

import pandas as pd

# 加载比亚迪所有 content_list.json
cache_dir = REPO_ROOT / "var/data/_mineru_cache/002594_比亚迪_annual_report_2025_20250325"
all_tables = []
for cl_file in sorted(cache_dir.glob("*_content_list.json")):
    with cl_file.open(encoding="utf-8") as f:
        data = json.load(f)
    for el in data:
        if isinstance(el, dict) and el.get("type") == "table" and el.get("table_body"):
            all_tables.append({
                "page_idx": el.get("page_idx", -1),
                "html": el.get("table_body", ""),
                "source": cl_file.name,
            })

print(f"总共 {len(all_tables)} 个含 HTML 的 table 元素")

# ============================================================
# 测试函数
# ============================================================
def test_table(name: str, table: dict, show_rows: int = 8):
    """测试 pandas 解析一张表，打印结果。"""
    print(f"\n{'='*80}")
    print(f"{name} (page_idx={table['page_idx']})")
    print(f"{'='*80}")

    html = table["html"]
    print(f"HTML 前 200 字: {html[:200]}")

    try:
        dfs = pd.read_html(StringIO(html))
        if not dfs:
            print("  ✗ pandas 未解析出表格")
            return False
        df = dfs[0]
        print(f"\n  ✓ DataFrame shape: {df.shape}")
        print(f"  列名: {list(df.columns)}")
        print(f"\n  前 {show_rows} 行:")
        print(df.head(show_rows).to_string(max_colwidth=25))
        return True
    except Exception as e:
        print(f"  ✗ 解析失败: {type(e).__name__}: {e}")
        return False


# ============================================================
# 按表类型分类查找
# ============================================================

def find_table_by_keywords(tables: list, must_have: list[str], all_must: bool = True) -> dict | None:
    """根据关键词找表。"""
    for t in tables:
        html = t["html"]
        if all_must:
            if all(kw in html for kw in must_have):
                return t
        else:
            if any(kw in html for kw in must_have):
                return t
    return None


# 1. 合并资产负债表
print("\n" + "█" * 80)
print("█ 1. 合并资产负债表（期间作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["货币资金", "存货", "资产总计"])
if t:
    test_table("合并资产负债表", t)

# 2. 合并利润表
print("\n" + "█" * 80)
print("█ 2. 合并利润表（期间作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["营业收入", "营业成本", "净利润"])
if t:
    test_table("合并利润表", t)

# 3. 合并现金流量表
print("\n" + "█" * 80)
print("█ 3. 合并现金流量表（期间作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["经营活动产生的现金流量净额", "投资活动产生的现金流量净额"])
if t:
    test_table("合并现金流量表", t)

# 4. 账龄表（应收账款账龄分桶）
print("\n" + "█" * 80)
print("█ 4. 账龄表（账龄分桶作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["1年以内", "1年至2年", "2年至3年"])
if not t:
    t = find_table_by_keywords(all_tables, ["账龄", "坏账准备"])
if t:
    test_table("应收账款账龄表", t)

# 5. 变动表（年初/本年增加/本年减少/年末）
print("\n" + "█" * 80)
print("█ 5. 变动表（年初余额/本年增加/本年减少/年末余额作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["年初余额", "本年增加", "本年减少", "年末余额"])
if t:
    test_table("变动表", t)

# 6. 净利润调节表（现金流量表补充资料）
print("\n" + "█" * 80)
print("█ 6. 净利润调节表（补充资料）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["净利润", "固定资产折旧", "经营活动产生的现金流量净额"])
if t:
    test_table("净利润调节表", t)

# 7. 所得税调节表
print("\n" + "█" * 80)
print("█ 7. 所得税调节表")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["利润总额", "按法定税率计算的所得税", "子公司适用不同税率"])
if t:
    test_table("所得税调节表", t)

# 8. 固定资产明细（资产类别作列）
print("\n" + "█" * 80)
print("█ 8. 固定资产明细（资产类别作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["房屋及建筑物", "机器设备", "运输工具", "办公及其他设备"])
if t:
    test_table("固定资产明细", t)

# 9. 双行表头（colspan/rowspan）
print("\n" + "█" * 80)
print("█ 9. 双行表头（colspan/rowspan 合并单元格）")
print("█" * 80)
# 找含 rowspan 或 colspan 的表
for t in all_tables:
    if 'rowspan="2"' in t["html"] or 'colspan="2"' in t["html"]:
        test_table("双行表头表", t)
        break

# 10. 权益变动表（权益科目作列，结构相反）
print("\n" + "█" * 80)
print("█ 10. 权益变动表（权益科目作列，结构相反）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["股本", "资本公积", "盈余公积", "未分配利润", "股东权益合计"])
if t:
    test_table("权益变动表", t)

# 11. 母公司资产负债表
print("\n" + "█" * 80)
print("█ 11. 母公司资产负债表")
print("█" * 80)
# 母公司报表通常在后面 page_idx 较大
parent_bs = None
for t in all_tables:
    if "货币资金" in t["html"] and "存货" in t["html"] and "资产总计" in t["html"]:
        # 跳过第一个（合并），找第二个（母公司）
        if parent_bs is None:
            parent_bs = t
            continue
        else:
            parent_bs = t
            break
if parent_bs:
    test_table("母公司资产负债表", parent_bs)

# 12. 分部报告（按业务分部）
print("\n" + "█" * 80)
print("█ 12. 分部报告（业务分部作列）")
print("█" * 80)
t = find_table_by_keywords(all_tables, ["报告分部", "手机部件", "汽车"])
if t:
    test_table("分部报告", t)

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
