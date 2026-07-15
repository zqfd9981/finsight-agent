"""比亚迪数据严格验证脚本。

验证内容：
1. tables.jsonl 总表数 + 含 HTML 表数
2. 三表数（资产负债表/利润表/现金流量表）+ 权益变动表
3. 注释表数（LLM 决策 keep=1 的章节下的表）
4. SQLite 中比亚迪数据分布（source_section / statement_type）
5. 30 个查询验证（三表 + 注释表 + 跨年度 + 母公司）
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for p in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ============================================================
# 路径配置
# ============================================================
DOC_ID = "002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2"
PARSED_DIR = REPO_ROOT / "var/data/parsed_filings" / DOC_ID
TABLES_JSONL = PARSED_DIR / "tables.jsonl"
ELEMENTS_JSONL = PARSED_DIR / "elements.jsonl"
NOTES_DECISION_FILE = REPO_ROOT / "var/data/notes_section_decisions/002594.json"
DB_PATH = REPO_ROOT / "var/data/structured_data/metrics.db"

_STATEMENT_KEYWORDS = ["资产负债表", "利润表", "现金流量表", "所有者权益变动表", "股东权益变动表"]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def classify_stmt_title(text: str) -> str | None:
    """识别报表标题文本，返回报表类型。

    报表标题格式："1、合并资产负债表"、"2、合并利润表" 等
    注释章节标题："61、现金流量表补充资料"、"60、现金流量表项目注释" 等
    区分：注释章节标题含"注释"或"补充资料"
    """
    t = text or ""
    # 排除"注释"类标题（如"60、现金流量表项目注释"）
    if "注释" in t:
        return None
    # 排除"补充资料"类标题（如"61、现金流量表补充资料"）
    if "补充资料" in t:
        return None
    has_balance = "资产负债表" in t
    has_income = "利润表" in t
    has_cash = "现金流量表" in t
    has_equity = "所有者权益变动表" in t or "股东权益变动表" in t
    if has_balance:
        return "balance_sheet"
    if has_income:
        return "income_statement"
    if has_cash:
        return "cash_flow_statement"
    if has_equity:
        return "equity_statement"
    return None


def build_page_ranges(elements: list[dict]) -> tuple[dict[int, str], set[int], dict[int, str]]:
    """识别三表区页码范围 + 注释区页码 + 注释章节标题。

    返回:
      stmt_page_map: page -> 报表类型(balance_sheet/income_statement/...)
      notes_pages: 注释区页码集合
      notes_section_titles: page -> 注释章节标题
    """
    # 1. 找出所有报表标题（按 page_start 排序）
    stmt_titles: list[tuple[int, str, str]] = []  # (page, stmt_type, text)
    notes_start_pages: list[int] = []
    notes_section_titles: dict[int, str] = {}
    notes_title_pattern = re.compile(r"^\d+、")
    in_notes_region = False

    for el in elements:
        text = str(el.get("text") or "").strip()
        page = int(el.get("page_start") or 0)
        if not text:
            continue
        # 注释区起点（"七、合并财务报表主要项目注释" 等）
        if "财务报表主要项目注释" in text and ("七、" in text or "十九、" in text or "公司财务" in text):
            notes_start_pages.append(page)
            in_notes_region = True
            continue
        # 注释章节标题（"1、货币资金" 等）
        if in_notes_region and notes_title_pattern.match(text):
            notes_section_titles[page] = text
            continue
        # 报表标题
        stmt_type = classify_stmt_title(text)
        if stmt_type:
            stmt_titles.append((page, stmt_type, text))

    # 获取 elements 中实际存在的页码集合（用于限制 stmt_page_map 范围）
    actual_pages = {int(el.get("page_start") or 0) for el in elements if el.get("page_start")}
    max_actual_page = max(actual_pages) if actual_pages else 0

    # 2. 收集所有"章节边界"页码：报表标题页 + 注释区起点页
    #    每个报表标题只覆盖到下一个章节边界前，避免越界覆盖注释区
    boundary_pages = sorted(set([p for p, _, _ in stmt_titles] + list(notes_start_pages)))

    stmt_page_map: dict[int, str] = {}
    stmt_titles.sort(key=lambda x: x[0])
    for i, (page, stmt_type, _) in enumerate(stmt_titles):
        # 找下一个边界页（大于当前 page 的最小边界页）
        next_boundary = max_actual_page + 1
        for bp in boundary_pages:
            if bp > page:
                next_boundary = bp
                break
        for p in range(page, next_boundary):
            if p in actual_pages:
                stmt_page_map[p] = stmt_type

    # 3. notes_pages：从 notes_start 最早页到 elements 最大页，排除三表区
    notes_pages: set[int] = set()
    if notes_start_pages:
        notes_start = min(notes_start_pages)
        for p in range(notes_start, max_actual_page + 1):
            if p in actual_pages and p not in stmt_page_map:
                notes_pages.add(p)

    return stmt_page_map, notes_pages, notes_section_titles


def find_nearest_notes_title(page: int, notes_section_titles: dict[int, str]) -> str | None:
    """找 page 之前最近的注释章节标题。"""
    candidates = [(p, t) for p, t in notes_section_titles.items() if p <= page]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def main() -> int:
    print("=" * 70)
    print("比亚迪数据严格验证")
    print("=" * 70)

    tables = load_jsonl(TABLES_JSONL)
    elements = load_jsonl(ELEMENTS_JSONL)
    stmt_page_map, notes_pages, notes_section_titles = build_page_ranges(elements)

    # ============================================================
    # 1. 统计 tables.jsonl
    # ============================================================
    print(f"\n[1] tables.jsonl 统计")
    print(f"  总表数: {len(tables)}")
    has_html = sum(1 for t in tables if (t.get("table_html") or "").strip())
    print(f"  含 table_html: {has_html}/{len(tables)}")

    # 三表区页码
    stmt_pages_set = set(stmt_page_map.keys())
    print(f"\n  三表区页码: p{min(stmt_pages_set)}-p{max(stmt_pages_set)} ({len(stmt_pages_set)} 页)")
    print(f"  注释区页码: p{min(notes_pages)}-p{max(notes_pages)} ({len(notes_pages)} 页)")
    print(f"  注释章节标题数: {len(notes_section_titles)}")

    # 按 page_start 分类表
    stmt_table_counts = Counter()
    notes_table_count = 0
    notes_skip_count = 0
    non_stmt_non_notes = 0
    stmt_table_details: dict[str, list[int]] = {}  # stmt_type -> [page_start, ...]

    # 加载 LLM 决策
    decisions = {}
    if NOTES_DECISION_FILE.exists():
        payload = json.loads(NOTES_DECISION_FILE.read_text(encoding="utf-8"))
        decisions = {d["title"]: d["keep"] for d in payload.get("decisions", [])}

    for t in tables:
        page_start = int(t.get("page_start") or 0)
        if page_start in stmt_page_map:
            stmt_type = stmt_page_map[page_start]
            stmt_table_counts[stmt_type] += 1
            stmt_table_details.setdefault(stmt_type, []).append(page_start)
        elif page_start in notes_pages:
            nearest_title = find_nearest_notes_title(page_start, notes_section_titles)
            keep = decisions.get(nearest_title, 0)
            if keep == 1:
                notes_table_count += 1
            else:
                notes_skip_count += 1
        else:
            non_stmt_non_notes += 1

    print(f"\n  按报表类型分类（按 page_start 落入三表区）:")
    for stmt_type in ["balance_sheet", "income_statement", "cash_flow_statement", "equity_statement"]:
        pages = stmt_table_details.get(stmt_type, [])
        page_str = f"p{min(pages)}-p{max(pages)}" if pages else "无"
        print(f"    {stmt_type:20s}: {stmt_table_counts[stmt_type]:3d} 张 ({page_str})")
    three_stmt_total = sum(stmt_table_counts[k] for k in ["balance_sheet", "income_statement", "cash_flow_statement"])
    print(f"  三表合计: {three_stmt_total}")
    print(f"  权益变动表: {stmt_table_counts['equity_statement']}")
    print(f"  注释区 keep=1 表数: {notes_table_count}")
    print(f"  注释区 keep=0 表数: {notes_skip_count}")
    print(f"  非三表非注释区: {non_stmt_non_notes}")

    # ============================================================
    # 2. LLM 注释章节决策分布
    # ============================================================
    print(f"\n[2] LLM 注释章节决策")
    keep_count = sum(1 for v in decisions.values() if v == 1)
    skip_count = sum(1 for v in decisions.values() if v == 0)
    print(f"  总章节: {len(decisions)}")
    print(f"  keep=1: {keep_count}")
    print(f"  keep=0: {skip_count}")

    # ============================================================
    # 3. SQLite 中比亚迪数据分布
    # ============================================================
    print(f"\n[3] SQLite 数据分布（表 metric_records）")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM metric_records WHERE company_code = ?", ("002594",))
    total_rows = cur.fetchone()[0]
    print(f"  比亚迪总记录数: {total_rows}")

    cur.execute(
        "SELECT source_section, COUNT(*) FROM metric_records WHERE company_code = ? GROUP BY source_section ORDER BY COUNT(*) DESC",
        ("002594",),
    )
    print(f"  source_section 分布:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]}")

    cur.execute(
        "SELECT statement_type, COUNT(*) FROM metric_records WHERE company_code = ? GROUP BY statement_type ORDER BY COUNT(*) DESC",
        ("002594",),
    )
    print(f"  statement_type 分布:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]}")

    cur.execute(
        "SELECT time_scope, COUNT(*) FROM metric_records WHERE company_code = ? GROUP BY time_scope ORDER BY COUNT(*) DESC",
        ("002594",),
    )
    print(f"  time_scope 分布:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]}")

    # 数据采样：source_section='unknown' 的前20条（看三表数据实际长什么样）
    print(f"\n  === 数据采样: source_section='unknown'（三表区）前 20 条 ===")
    cur.execute(
        "SELECT metric_name, metric_label, time_scope, value, period_end, statement_type FROM metric_records WHERE company_code = '002594' AND source_section = 'unknown' LIMIT 20"
    )
    for row in cur.fetchall():
        print(f"    {row['metric_name']:40s} | {row['metric_label']:25s} | {row['time_scope']:15s} | {row['value']:20s} | {row['period_end']} | {row['statement_type']}")

    # 数据采样：source_section='notes' 的前10条
    print(f"\n  === 数据采样: source_section='notes'（注释区）前 10 条 ===")
    cur.execute(
        "SELECT metric_name, metric_label, time_scope, value, period_end, statement_type FROM metric_records WHERE company_code = '002594' AND source_section = 'notes' LIMIT 10"
    )
    for row in cur.fetchall():
        print(f"    {row['metric_name']:40s} | {row['metric_label']:25s} | {row['time_scope']:15s} | {row['value']:20s} | {row['period_end']} | {row['statement_type']}")

    # 看 source_section='unknown' 的 metric_name 分布
    print(f"\n  === source_section='unknown' 的 metric_name 分布（前 20）===")
    cur.execute(
        "SELECT metric_name, metric_label, COUNT(*) as cnt FROM metric_records WHERE company_code = '002594' AND source_section = 'unknown' GROUP BY metric_name, metric_label ORDER BY cnt DESC LIMIT 20"
    )
    for row in cur.fetchall():
        print(f"    {row['metric_name']:40s} | {row['metric_label']:30s} | {row['cnt']}")

    # ============================================================
    # 4. 30 个查询验证
    # ============================================================
    print(f"\n[4] 30 个查询验证")
    print("-" * 70)

    # 说明：比亚迪三表 source_section 多为 'unknown'（TableExtractor 未细分），
    #       time_scope 经 _normalize_time_scope 归一化后均为 'YYYY年'（'2024年度'→'2024年'）。
    #       注释区 source_section='notes'，指标名是明细项（如"主营业务收入""职工福利费"）。
    queries = [
        # === 三表-资产负债表（合并）===
        (1, "三表-资产负债表", "货币资金 2024年",
         "metric_label = '货币资金' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (2, "三表-资产负债表", "应收账款 2024年（三表，排除注释）",
         "metric_label = '应收账款' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (3, "三表-资产负债表", "存货 2024年",
         "metric_label = '存货' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (4, "三表-资产负债表", "固定资产 2024年（三表，排除注释）",
         "metric_label = '固定资产' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (5, "三表-资产负债表", "短期借款 2024年",
         "metric_label = '短期借款' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (6, "三表-资产负债表", "长期借款 2024年（三表，排除注释）",
         "metric_label = '长期借款' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (7, "三表-资产负债表", "资产总计 2024年",
         "metric_label = '资产总计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (8, "三表-资产负债表", "负债合计 2024年",
         "metric_label = '负债合计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (9, "三表-资产负债表", "股东权益合计 2024年",
         "metric_label = '股东权益合计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (10, "三表-资产负债表", "归属于母公司股东权益合计 2024年",
         "metric_label = '归属于母公司股东权益合计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        # === 三表-利润表 ===（time_scope 归一化为 '2024年'）
        (11, "三表-利润表", "营业收入 2024年",
         "metric_label LIKE '%营业收入%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (12, "三表-利润表", "营业成本 2024年",
         "metric_label LIKE '%营业成本%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (13, "三表-利润表", "净利润 2024年",
         "metric_label LIKE '%净利润%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (14, "三表-利润表", "归属于母公司所有者的净利润 2024年",
         "metric_label LIKE '%归属于母公司%' AND metric_label LIKE '%净利润%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (15, "三表-利润表", "基本每股收益 2024年",
         "metric_label LIKE '%基本每股收益%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (16, "三表-利润表", "研发费用 2024年",
         "metric_label = '研发费用' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        # === 三表-现金流量表 ===
        (17, "三表-现金流量表", "经营活动产生的现金流量净额 2024年",
         "metric_label LIKE '%经营活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (18, "三表-现金流量表", "投资活动现金流量净额 2024年",
         "metric_label LIKE '%投资活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (19, "三表-现金流量表", "筹资活动现金流量净额 2024年",
         "metric_label LIKE '%筹资活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (20, "三表-现金流量表", "年末现金及现金等价物余额 2024年",
         "metric_label LIKE '%年末现金及现金等价物余额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        # === 注释表 LLM keep=1 指标（注释区指标名为明细项，不是报表原词）===
        (21, "注释-keep", "营业收入和营业成本明细 (注释区: 主营/其他业务收入)",
         "metric_label IN ('主营业务收入', '其他业务收入') AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (22, "注释-keep", "管理费用明细 (注释区: 职工福利费/社保/折旧)",
         "metric_label IN ('职工福利费', '社会保险费', '折旧及摊销') AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (23, "注释-keep", "固定资产明细 (注释区)",
         "metric_label LIKE '%固定资产%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (24, "注释-keep", "所得税费用调节 (注释区)",
         "metric_label LIKE '%所得税费用%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (25, "注释-keep", "递延所得税资产/负债 (注释区)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND metric_label LIKE '%递延所得税%'"),
        # === 跨年度对比（2024 vs 2023）===
        (26, "跨年度", "货币资金 2024 vs 2023",
         "metric_label = '货币资金' AND time_scope IN ('2024年', '2023年') AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (27, "跨年度", "存货 2024 vs 2023",
         "metric_label = '存货' AND time_scope IN ('2024年', '2023年') AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        (28, "跨年度", "资产总计 2024 vs 2023",
         "metric_label = '资产总计' AND time_scope IN ('2024年', '2023年') AND statement_type = 'consolidated' AND source_section = 'unknown'"),
        # === 母公司报表 ===（time_scope='2024年'，source_section='unknown'）
        (29, "母公司", "母公司净利润 2024年",
         "metric_label = '净利润' AND time_scope = '2024年' AND statement_type = 'parent_only' AND source_section = 'unknown'"),
        (30, "母公司", "母公司营业收入 2024年",
         "metric_label LIKE '%营业收入%' AND time_scope = '2024年' AND statement_type = 'parent_only' AND source_section = 'unknown'"),
    ]

    pass_count = 0
    fail_count = 0
    for qid, category, desc, where_clause in queries:
        sql = f"SELECT metric_name, metric_label, time_scope, value, period_end, source_section, statement_type FROM metric_records WHERE company_code = '002594' AND {where_clause} ORDER BY time_scope, source_section"
        cur.execute(sql)
        rows = cur.fetchall()
        if rows:
            pass_count += 1
            print(f"  [Q{qid:02d}] ✓ {category} | {desc} | {len(rows)} 条")
            for r in rows[:3]:
                print(f"         {r['metric_label']} | {r['time_scope']} | {r['value']} | {r['period_end']} | {r['source_section']}/{r['statement_type']}")
            if len(rows) > 3:
                print(f"         ... 还有 {len(rows) - 3} 条")
        else:
            fail_count += 1
            print(f"  [Q{qid:02d}] ✗ {category} | {desc} | 0 条 ❌")

    print("-" * 70)
    print(f"查询结果: 通过 {pass_count}/30, 失败 {fail_count}/30")

    conn.close()
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
