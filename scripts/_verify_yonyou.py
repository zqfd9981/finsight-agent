"""用友网络（600588）数据严格验证脚本。

验证维度（30 个查询，注释表占比 40%）：
  Q01-Q08  三表-资产负债表（8个）
  Q09-Q12  三表-利润表（4个）
  Q13-Q15  三表-现金流量表（3个）
  Q16-Q27  注释区 LLM keep=1 指标（12个，40%）
  Q28-Q29  跨年度对比（2个）
  Q30      母公司报表（1个）

用友网络数据特征（与比亚迪不同）：
  - source_section 细分了三表类型（balance_sheet/income_statement/cash_flow_statement/equity_statement）
  - time_scope：三表区 '2024年'/'2023年'，注释区 '期末余额'/'期初余额'，利润表部分 '本期'/'上期'
  - 所有者权益合计 label 为"所有者权益(或股东权益)合计"
  - 归母净利润 label 为"1.归属于母公司股东的净利润(净亏损以"-"号填列)"
  - 注释区指标名是明细项（库存现金/银行存款/应收账款坏账准备 等）
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC_ID = "600588_用友网络__annual__2025__600588_用友网络_annual_report_2025_20250329__structured_v2"
PARSED_DIR = REPO / "var/data/parsed_filings" / DOC_ID
TABLES_JSONL = PARSED_DIR / "tables.jsonl"
ELEMENTS_JSONL = PARSED_DIR / "elements.jsonl"
NOTES_DECISION_FILE = REPO / "var/data/notes_section_decisions/600588.json"
DB_PATH = REPO / "var/data/structured_data/metrics.db"
CC = "600588"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def main() -> None:
    # ============================================================
    # [1] tables.jsonl 统计
    # ============================================================
    print("=" * 70)
    print("[1] tables.jsonl 统计")
    print("=" * 70)
    tables = load_jsonl(TABLES_JSONL)
    print(f"  总表数: {len(tables)}")
    has_html = sum(1 for t in tables if (t.get("table_html") or "").strip())
    print(f"  含 table_html: {has_html}/{len(tables)}")

    # 页码范围
    pages = [int(t.get("page_start") or 0) for t in tables if t.get("page_start")]
    if pages:
        print(f"  页码范围: p{min(pages)}-p{max(pages)}")

    # 三表区 vs 注释区（用友网络 source_section 已细分）
    print(f"  注：source_section 在 TableExtractor 中已细分，见 [3] SQLite 分布")

    # ============================================================
    # [2] LLM 注释章节决策
    # ============================================================
    print("\n" + "=" * 70)
    print("[2] LLM 注释章节决策")
    print("=" * 70)
    if NOTES_DECISION_FILE.exists():
        data = json.loads(NOTES_DECISION_FILE.read_text(encoding="utf-8"))
        decisions = data.get("decisions", [])
        keep = sum(1 for d in decisions if d.get("keep") == 1)
        skip = sum(1 for d in decisions if d.get("keep") == 0)
        print(f"  总章节: {len(decisions)}, keep=1: {keep}, keep=0: {skip}")
    else:
        print("  无 LLM 决策缓存")

    # ============================================================
    # [3] SQLite 数据分布
    # ============================================================
    print("\n" + "=" * 70)
    print("[3] SQLite 数据分布")
    print("=" * 70)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM metric_records WHERE company_code=?", (CC,))
    print(f"  用友网络总记录数: {cur.fetchone()[0]}")

    cur.execute(
        "SELECT source_section, COUNT(*) FROM metric_records WHERE company_code=? GROUP BY source_section ORDER BY COUNT(*) DESC",
        (CC,),
    )
    print("  source_section 分布:")
    for r in cur.fetchall():
        print(f"    {r['source_section']:25s}: {r[1]}")

    cur.execute(
        "SELECT statement_type, COUNT(*) FROM metric_records WHERE company_code=? GROUP BY statement_type",
        (CC,),
    )
    print("  statement_type 分布:")
    for r in cur.fetchall():
        print(f"    {r['statement_type']:20s}: {r[1]}")

    # ============================================================
    # [4] 30 个查询验证
    # ============================================================
    print("\n" + "=" * 70)
    print("[4] 30 个查询验证")
    print("=" * 70)

    # 查询定义：(编号, 分类, 描述, where_clause)
    # 用友网络 source_section 已细分，可用精确值
    # time_scope: 资产负债表 '2024年', 利润表 '2024年'/'本期', 现金流量表 '2024年', 注释区 '期末余额'
    queries = [
        # === 三表-资产负债表（合并）=== source_section='balance_sheet', time_scope='2024年'
        (1, "三表-资产负债表", "货币资金 2024年",
         "metric_label = '货币资金' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (2, "三表-资产负债表", "应收账款 2024年（三表，排除注释）",
         "metric_label = '应收账款' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (3, "三表-资产负债表", "存货 2024年",
         "metric_label = '存货' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (4, "三表-资产负债表", "资产总计 2024年",
         "metric_label = '资产总计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (5, "三表-资产负债表", "负债合计 2024年",
         "metric_label = '负债合计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (6, "三表-资产负债表", "所有者权益合计 2024年",
         "metric_label = '所有者权益(或股东权益)合计' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (7, "三表-资产负债表", "归母权益 2024年",
         "metric_label LIKE '%归属于母公司所有者权益%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (8, "三表-资产负债表", "少数股东权益 2024年",
         "metric_label = '少数股东权益' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        # === 三表-利润表（合并）=== source_section='income_statement'
        (9, "三表-利润表", "营业收入 2024年",
         "metric_label LIKE '%营业收入%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'income_statement'"),
        (10, "三表-利润表", "净利润 2024年",
         "metric_label LIKE '%净利润%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'income_statement'"),
        (11, "三表-利润表", "归属于母公司股东的净利润 2024年",
         "metric_label LIKE '%归属于母公司股东%净利润%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'income_statement'"),
        (12, "三表-利润表", "研发费用 2024年（利润表）",
         "metric_label LIKE '%研发费用%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'income_statement'"),
        # === 三表-现金流量表（合并）=== source_section='cash_flow_statement'
        (13, "三表-现金流量表", "经营活动产生的现金流量净额 2024年",
         "metric_label LIKE '%经营活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'cash_flow_statement'"),
        (14, "三表-现金流量表", "投资活动现金流量净额 2024年",
         "metric_label LIKE '%投资活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'cash_flow_statement'"),
        (15, "三表-现金流量表", "筹资活动现金流量净额 2024年",
         "metric_label LIKE '%筹资活动%现金流量净额%' AND time_scope = '2024年' AND statement_type = 'consolidated' AND source_section = 'cash_flow_statement'"),
        # === 注释区 LLM keep=1 指标（12个，40%）=== source_section='notes', time_scope='期末余额'
        (16, "注释-keep", "货币资金明细: 库存现金 (注释区)",
         "metric_label = '库存现金' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (17, "注释-keep", "货币资金明细: 银行存款 (注释区)",
         "metric_label = '银行存款' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (18, "注释-keep", "应收账款坏账准备 (注释区)",
         "metric_label LIKE '%应收账款坏账准备%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (19, "注释-keep", "合同资产减值准备 (注释区)",
         "metric_label LIKE '%合同资产减值准备%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (20, "注释-keep", "营业收入明细 (注释区: 营业收入金额)",
         "metric_label LIKE '%营业收入金额%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (21, "注释-keep", "研发费用明细 (注释区: 按费用性质列示)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND metric_label IN ('工资及福利费', '折旧及摊销', '办公费', '差旅费', '咨询费', '服务费', '其他')"),
        (22, "注释-keep", "投资收益明细 (注释区)",
         "metric_label LIKE '%投资收益%' AND source_section = 'notes' AND statement_type = 'consolidated' AND time_scope IN ('本期', '上期')"),
        (23, "注释-keep", "信用减值损失 (注释区)",
         "metric_label LIKE '%信用减值损失%' AND source_section = 'notes' AND statement_type = 'consolidated'"),
        (24, "注释-keep", "所得税费用调节 (注释区: 会计利润与所得税费用调整)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND source_caption LIKE '%会计利润与所得税费用调整%'"),
        (25, "注释-keep", "现金流量表补充资料 (注释区)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND source_caption LIKE '%现金流量表补充资料%'"),
        (26, "注释-keep", "非经常性损益明细 (注释区)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND source_caption LIKE '%非经常性损益%'"),
        (27, "注释-keep", "外币货币性项目 (注释区)",
         "source_section = 'notes' AND statement_type = 'consolidated' AND metric_label LIKE '%外币%'"),
        # === 跨年度对比（2024 vs 2023）===
        (28, "跨年度", "货币资金 2024 vs 2023",
         "metric_label = '货币资金' AND time_scope IN ('2024年', '2023年') AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        (29, "跨年度", "资产总计 2024 vs 2023",
         "metric_label = '资产总计' AND time_scope IN ('2024年', '2023年') AND statement_type = 'consolidated' AND source_section = 'balance_sheet'"),
        # === 母公司报表 ===
        (30, "母公司", "母公司货币资金 2024年",
         "metric_label = '货币资金' AND time_scope = '2024年' AND statement_type = 'parent_only' AND source_section = 'balance_sheet'"),
    ]

    passed = 0
    failed = 0
    for qid, category, desc, where_clause in queries:
        sql = f"SELECT metric_label, time_scope, value, source_section, statement_type, source_caption FROM metric_records WHERE company_code = '{CC}' AND {where_clause} LIMIT 3"
        cur.execute(sql)
        rows = cur.fetchall()
        if rows:
            passed += 1
            r = rows[0]
            val_display = r["value"][:25] if r["value"] else ""
            cap_display = (r["source_caption"] or "")[:30]
            print(f"  Q{qid:02d} ✓ [{category}] {desc}")
            print(f"        → {r['metric_label'][:30]} | {r['time_scope']} | {val_display} | {r['source_section']}")
            if cap_display:
                print(f"        caption: {cap_display}")
        else:
            failed += 1
            print(f"  Q{qid:02d} ✗ [{category}] {desc}")
            print(f"        → 0 条记录")

    print(f"\n{'=' * 70}")
    print(f"  30 个查询验证: 通过 {passed}/30, 失败 {failed}/30")
    print(f"{'=' * 70}")

    conn.close()


if __name__ == "__main__":
    main()
