"""三一重工 + 海尔智家 值对账：SQLite 值 vs 原始 HTML 值。

同时检测：
- 三表完整性（合并/母公司各 4 类是否齐全）
- 注释区是否存在
- 值精确匹配
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "var/data/structured_data/metrics.db"
PARSED_ROOT = REPO / "var/data/parsed_filings"

COMPANIES = [
    ("600031", "三一重工", "600031_三一重工__annual__2025__600031_三一重工_annual_report_2025_20250418__structured"),
    ("600690", "海尔智家", "600690_海尔智家__annual__2025__600690_海尔智家_annual_report_2025_20250328__structured"),
]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def find_table_by_section(tables: list[dict], section_keyword: str) -> dict | None:
    """按 section_path 关键词找第一张含 table_html 的表。"""
    for t in tables:
        sp = " > ".join(t.get("section_path") or [])
        if section_keyword in sp and (t.get("table_html") or "").strip():
            return t
    return None


def extract_value_from_html(html: str, label_pattern: str) -> str | None:
    """从 HTML 表格中按指标名标签提取数值列（跳过附注列）。"""
    if not html:
        return None
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
    cell_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
    note_pattern = re.compile(r"^[一二三四五六七八九十百]+、\d+$")
    num_pattern = re.compile(r"^[-(]?\d{1,3}(,\d{3})+[-)]?$|^[-(]?\d+\.?\d*[-)]?$")

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cell_pattern.findall(row_html)]
        if not cells:
            continue
        if not re.search(label_pattern, cells[0]):
            continue
        for v in cells[1:]:
            if not v:
                continue
            if note_pattern.match(v):
                continue
            if num_pattern.match(v):
                return v
        for v in cells[1:]:
            if v and re.search(r"[\d,\-]", v) and not note_pattern.match(v):
                return v
        return None
    return None


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    for cc, name, doc_dir in COMPANIES:
        print("=" * 90)
        print(f"[{cc} {name}]")
        print("=" * 90)

        tables = load_jsonl(PARSED_ROOT / doc_dir / "tables.jsonl")
        print(f"  tables.jsonl: {len(tables)} 张表")

        # === 三表完整性检查 ===
        print("\n  [三表完整性检查]")
        stmt_types = ["合并资产负债表", "合并利润表", "合并现金流量表", "合并所有者权益变动表",
                       "母公司资产负债表", "母公司利润表", "母公司现金流量表", "母公司所有者权益变动表"]
        for sp_name in stmt_types:
            t = find_table_by_section(tables, sp_name)
            sqlite_count = 0
            cur.execute(
                "SELECT COUNT(*) FROM metric_records WHERE company_code=? AND source_caption LIKE ?",
                (cc, f"%{sp_name}%"),
            )
            sqlite_count = cur.fetchone()[0]
            status = "✓" if t else "✗ 缺失"
            print(f"    {sp_name:20s}: HTML={'有' if t else '无'}  SQLite={sqlite_count:4d}  {status}")

        # === 注释区检查 ===
        print("\n  [注释区检查]")
        notes_tables = [t for t in tables if any(
            kw in " > ".join(t.get("section_path") or [])
            for kw in ("货币资金", "应收账款", "固定资产", "营业收入", "存货", "长期股权投资")
        )]
        cur.execute(
            "SELECT COUNT(*) FROM metric_records WHERE company_code=? AND source_section='notes'",
            (cc,),
        )
        notes_sqlite = cur.fetchone()[0]
        print(f"    structured 目录中注释区表: {len(notes_tables)} 张")
        print(f"    SQLite notes 记录数: {notes_sqlite}")
        if notes_tables and notes_sqlite == 0:
            print(f"    ⚠ 注释区表存在但未入库！TableExtractor 注释区识别失败")
        elif not notes_tables and notes_sqlite == 0:
            print(f"    ⚠ structured_pages 未配置注释区页码")

        # === 值对账 ===
        print("\n  [值对账: SQLite vs 原始 HTML]")

        def sqlite_value(where_clause: str) -> tuple[str, str] | None:
            cur.execute(
                f"SELECT metric_label, time_scope, value FROM metric_records "
                f"WHERE company_code = '{cc}' AND {where_clause} LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return row["value"], f"{row['metric_label']} | {row['time_scope']}"
            return None

        # 对账项：(项名, section_path关键词, HTML label正则, SQLite where_clause)
        items = [
            ("货币资金", "合并资产负债表", r"^货币资金$",
             "metric_label='货币资金' AND time_scope='2024年' AND source_section='balance_sheet' AND statement_type='consolidated'"),
            ("资产总计", "合并资产负债表", r"^资产总计$",
             "metric_label='资产总计' AND time_scope='2024年' AND source_section='balance_sheet' AND statement_type='consolidated'"),
            ("营业总收入", "合并利润表", r"营业总收入",
             "metric_label LIKE '%营业总收入%' AND time_scope='2024年' AND source_section='income_statement' AND statement_type='consolidated'"),
            ("净利润", "合并利润表", r"净利润",
             "metric_label LIKE '%净利润%' AND time_scope='2024年' AND source_section='income_statement' AND statement_type='consolidated'"),
            ("归母权益", "合并资产负债表", r"归属于母公司",
             "metric_label LIKE '%归属于母公司%权益%合计%' AND time_scope='2024年' AND source_section='balance_sheet' AND statement_type='consolidated'"),
        ]

        print(f"    {'项名':12s} {'SQLite值':>25s}  {'HTML值':>25s}  {'一致':4s}  备注")
        print("    " + "-" * 85)

        pass_cnt = 0
        fail_cnt = 0
        skip_cnt = 0
        for item_name, sec_kw, label_re, where_clause in items:
            sv = sqlite_value(where_clause)
            sqlite_val = sv[0] if sv else ""
            sqlite_note = sv[1] if sv else "未找到"

            t = find_table_by_section(tables, sec_kw)
            html_val = None
            if t:
                html_val = extract_value_from_html(t.get("table_html") or "", label_re)

            if not sqlite_val and not html_val:
                print(f"    {item_name:12s} {'(无数据)':>25s}  {'(无数据)':>25s}  {'跳过':4s}  两端均无（structured_pages 缺失）")
                skip_cnt += 1
                continue

            s_norm = (sqlite_val or "").replace(",", "").strip()
            h_norm = (html_val or "").replace(",", "").strip()
            if s_norm and h_norm and s_norm == h_norm:
                match = "✓"
                pass_cnt += 1
            elif s_norm and h_norm and (s_norm in h_norm or h_norm in s_norm):
                match = "≈"
                pass_cnt += 1
            else:
                match = "✗"
                fail_cnt += 1

            print(f"    {item_name:12s} {sqlite_val:>25s}  {(html_val or 'N/A'):>25s}  {match:4s}  {sqlite_note}")

        total = pass_cnt + fail_cnt + skip_cnt
        print(f"\n    对账结果: 通过 {pass_cnt}/{total}  失败 {fail_cnt}  跳过 {skip_cnt}(缺数据)")
        print()

    conn.close()


if __name__ == "__main__":
    main()
