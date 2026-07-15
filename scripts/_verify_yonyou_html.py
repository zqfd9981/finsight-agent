"""用友网络值对账：从 tables.jsonl 原始 HTML 提取关键指标值，与 SQLite 比对。

对账指标：
  - 三表：货币资金、资产总计、营业收入、净利润、归母净利润
  - 注释区：库存现金、银行存款（货币资金明细）、利润总额（所得税调节）
  - 跨表一致性：库存现金 + 银行存款 + 其他货币资金 ≈ 三表货币资金
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC_ID = "600588_用友网络__annual__2025__600588_用友网络_annual_report_2025_20250329__structured_v2"
PARSED_DIR = REPO / "var/data/parsed_filings" / DOC_ID
TABLES_JSONL = PARSED_DIR / "tables.jsonl"
DB_PATH = REPO / "var/data/structured_data/metrics.db"
CC = "600588"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def find_table_by_section(tables: list[dict], section_keyword: str) -> dict | None:
    """按 section_path 关键词找表（取第一张含 table_html 的）。"""
    for t in tables:
        sp = " > ".join(t.get("section_path") or [])
        if section_keyword in sp and (t.get("table_html") or "").strip():
            return t
    return None


def extract_value_from_html(html: str, label_pattern: str, col: int = 1) -> str | None:
    """从 HTML 表格中按指标名标签提取数值列。

    策略：
    - 匹配第一列（指标名）符合 label_pattern 的行
    - 跳过附注列（含"七、X"格式的注释号或纯数字短串）
    - 取第一个真正含千分位逗号或纯数字的列
    """
    if not html:
        return None
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
    cell_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)

    # 附注列特征：含中文+顿号+数字（如"七、1"、"七、61"），或长度≤4 且是纯"附注"/"注"
    note_pattern = re.compile(r"^[一二三四五六七八九十百]+、\d+$")
    # 真正数值列特征：含千分位逗号或纯数字（可带负号/括号）
    num_pattern = re.compile(r"^[-(]?\d{1,3}(,\d{3})+[-)]?$|^[-(]?\d+\.?\d*[-)]?$")

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cell_pattern.findall(row_html)]
        if not cells:
            continue
        # 第一列匹配指标名（用 search 而非 match，允许前缀如"其中:"）
        if not re.search(label_pattern, cells[0]):
            continue
        # 跳过附注列，找真正数值
        for v in cells[1:]:
            if not v:
                continue
            if note_pattern.match(v):
                continue
            if num_pattern.match(v):
                return v
        # 如果严格数值匹配失败，取第一个含数字的列
        for v in cells[1:]:
            if v and re.search(r"[\d,\-]", v) and not note_pattern.match(v):
                return v
        return None
    return None


def main() -> None:
    tables = load_jsonl(TABLES_JSONL)
    print(f"加载 {len(tables)} 张表")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    def sqlite_value(where_clause: str) -> tuple[str, str] | None:
        cur.execute(
            f"SELECT metric_label, time_scope, value FROM metric_records "
            f"WHERE company_code = '{CC}' AND {where_clause} LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            return row["value"], f"{row['metric_label']} | {row['time_scope']}"
        return None

    # ============================================================
    # 对账项：(项名, section_path 关键词, HTML label 正则, SQLite where_clause)
    # ============================================================
    items = [
        ("货币资金(资产负债表)", "合并资产负债表", r"^货币资金$",
         "metric_label='货币资金' AND time_scope='2024年' AND source_section='balance_sheet' AND statement_type='consolidated'"),
        ("资产总计", "合并资产负债表", r"^资产总计$",
         "metric_label='资产总计' AND time_scope='2024年' AND source_section='balance_sheet' AND statement_type='consolidated'"),
        ("营业收入(利润表)", "合并利润表", r"营业收入$",
         "metric_label LIKE '%营业收入%' AND time_scope='2024年' AND source_section='income_statement' AND statement_type='consolidated'"),
        ("净利润(利润表)", "合并利润表", r"净利润",
         "metric_label LIKE '%净利润%' AND time_scope='2024年' AND source_section='income_statement' AND statement_type='consolidated'"),
        ("库存现金(注释:货币资金)", "1、 货币资金", r"^库存现金$",
         "metric_label='库存现金' AND source_section='notes' AND statement_type='consolidated' AND time_scope='期末余额'"),
        ("银行存款(注释:货币资金)", "1、 货币资金", r"^银行存款$",
         "metric_label='银行存款' AND source_section='notes' AND statement_type='consolidated' AND time_scope='期末余额'"),
        ("利润总额(注释:所得税调节)", "会计利润与所得税费用调整", r"^利润总额$",
         "source_caption LIKE '%会计利润与所得税费用调整%' AND source_section='notes' AND statement_type='consolidated'"),
    ]

    print("\n" + "=" * 90)
    print(f"{'项名':30s} {'SQLite值':>22s}  {'HTML值':>22s}  {'一致':4s}  备注")
    print("=" * 90)

    pass_cnt = 0
    fail_cnt = 0
    for name, sec_kw, label_re, where_clause in items:
        sv = sqlite_value(where_clause)
        sqlite_val = sv[0] if sv else "0"
        sqlite_note = sv[1] if sv else "未找到"

        # 从原始 HTML 提取
        t = find_table_by_section(tables, sec_kw)
        html_val = None
        if t:
            html_val = extract_value_from_html(t.get("table_html") or "", label_re)

        # 数值归一化比较：去逗号
        s_norm = (sqlite_val or "").replace(",", "").strip()
        h_norm = (html_val or "").replace(",", "").strip()
        if s_norm and h_norm and s_norm == h_norm:
            match = "✓"
            pass_cnt += 1
        elif s_norm and h_norm and s_norm in h_norm:
            match = "≈"
            pass_cnt += 1
        else:
            match = "✗"
            fail_cnt += 1

        print(f"{name:30s} {sqlite_val:>22s}  {(html_val or 'N/A'):>22s}  {match:4s}  {sqlite_note}")

    print("=" * 90)
    print(f"\n对账结果: 通过 {pass_cnt}/{pass_cnt + fail_cnt}")

    # ============================================================
    # 跨表一致性：库存现金 + 银行存款 + 其他 ≈ 三表货币资金
    # ============================================================
    print("\n" + "=" * 90)
    print("[跨表一致性] 货币资金明细（注释）合计 vs 三表货币资金")
    print("=" * 90)

    cur.execute(
        "SELECT metric_label, value FROM metric_records "
        "WHERE company_code=? AND source_section='notes' AND statement_type='consolidated' "
        "AND time_scope='期末余额' AND source_caption LIKE '%货币资金%'",
        (CC,),
    )
    detail_rows = cur.fetchall()
    print(f"  注释区'货币资金'章节下的明细项（{len(detail_rows)} 条）：")
    detail_total = 0
    for r in detail_rows:
        v = r["value"].replace(",", "")
        try:
            num = float(v)
        except ValueError:
            continue
        print(f"    {r['metric_label']:25s}: {r['value']}")
        if r["metric_label"] not in ("库存现金", "银行存款", "其他货币资金"):
            continue
        detail_total += num

    cur.execute(
        "SELECT value FROM metric_records "
        "WHERE company_code=? AND metric_label='货币资金' AND time_scope='2024年' "
        "AND source_section='balance_sheet' AND statement_type='consolidated'",
        (CC,),
    )
    bs_row = cur.fetchone()
    bs_val = float(bs_row["value"].replace(",", "")) if bs_row else 0

    print(f"\n  三表货币资金 2024年       : {bs_val:,.0f}")
    print(f"  注释区明细合计（现金+银行+其他）: {detail_total:,.0f}")
    print(f"  差异                     : {bs_val - detail_total:,.0f}")
    if abs(bs_val - detail_total) < 1:
        print("  → 完全一致 ✓")
    elif abs(bs_val - detail_total) / bs_val < 0.05:
        print(f"  → 差异 <5%（可能注释区只列了部分明细项）")
    else:
        print("  → 差异较大，需人工核对")

    conn.close()


if __name__ == "__main__":
    main()
