"""验证跨页表格完整性：检查每张大表是否包含关键汇总行。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

tables = []
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

# 每类表的关键汇总行（必须在完整表里出现）
KEY_ROWS = {
    "资产负债表": ["资产总计", "负债合计", "所有者权益合计"],
    "利润表": ["营业收入", "净利润", "基本每股收益"],
    "现金流量表": ["经营活动产生的现金流量净额", "期末现金及现金等价物余额"],
    "权益变动表": ["本期期末余额", "本年期初余额"],
}

# 检查每张大表（行数>20的A类表）
print("=== 跨页大表完整性检查 ===\n")
for i, tbl in enumerate(sorted(tables, key=lambda t: t.get("page_start", 0)), 1):
    md = tbl.get("table_markdown", "")
    rows = md.count("\n") + 1
    if rows < 20:
        continue

    page = tbl.get("page_start", 0)
    section = " > ".join(tbl.get("section_path", []))[:30]

    # 判断表类型
    table_type = None
    for key in KEY_ROWS:
        if key in md or key.replace("表", "") in md:
            # 更精确：看表头或内容
            if "资产负债" in md or ("资产总计" in md and "负债合计" in md):
                table_type = "资产负债表"
                break
            if "营业总收入" in md or "营业收入" in md:
                table_type = "利润表"
                break
            if "经营活动产生的现金流量" in md:
                table_type = "现金流量表"
                break
            if "本期期末余额" in md or "所有者权益合计" in md and "股本" in md:
                table_type = "权益变动表"
                break

    print(f"[{i}] p{page} ({rows}行) | 推断类型: {table_type or '未知'}")

    if table_type:
        key_rows = KEY_ROWS[table_type]
        found = {kr: kr in md for kr in key_rows}
        for kr, ok in found.items():
            icon = "✓" if ok else "✗"
            print(f"     {icon} {kr}")
        if all(found.values()):
            print(f"     → 完整 ✓")
        else:
            print(f"     → 不完整 ✗（缺少关键行）")

    # 看最后3行
    lines = md.strip().split("\n")
    print(f"     最后3行:")
    for line in lines[-3:]:
        print(f"       {line[:100]}")
    print()
