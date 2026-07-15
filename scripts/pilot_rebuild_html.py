"""试点：从 v1 缓存零成本重建带 html 的 tables.jsonl，对比 markdown 旧路线提取质量。

关键思路（用户核心诉求）：
  - 现有 88 家的 tables.jsonl 是"旧 markdown 路线"产物（table_html 全为空），
    但 MinerU v1 缓存的 content_list 仍保留 table_body(html)。
  - 本脚本从 v1 缓存把 html 注入现有 65 张表，零 MinerU API 调用，
    再用当前 HTML-first 提取器重提，对比 metrics.db 里的旧值。

安全约束：
  - 只读 metrics.db，不写库、不动其他 87 家公司、不调 MinerU。
  - 运行前自动备份 metrics.db 到 var/data/_pilot_backup/。

用法：
    python scripts/pilot_rebuild_html.py --company-code 600519
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _c in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(_c) not in sys.path:
        sys.path.insert(0, str(_c))

from finsight_agent.config.settings import load_settings  # noqa: E402
from finsight_agent.capabilities.structured_data.metric_normalizer import (  # noqa: E402
    MetricNormalizer,
)
from finsight_agent.capabilities.structured_data.table_extractor import (  # noqa: E402
    TableExtractor,
)
from finsight_agent.capabilities.structured_data.cross_page_repair import (  # noqa: E402
    find_truncated_tables,
    check_table_completeness,
    infer_table_type,
    merge_pages_to_single_pdf,
)
from finsight_agent.infra.document_parsers.mineru_parser import (  # noqa: E402
    _normalize_content_list,
)

PAGE_FILTER_JSON = REPO_ROOT / "var" / "data" / "page_filter" / "annual_2025_pages.json"
MINERU_CACHE_DIR = REPO_ROOT / "var" / "data" / "_mineru_cache"
BACKUP_DIR = REPO_ROOT / "var" / "data" / "_pilot_backup"


# ============================================================
# 1. 挑选与 structured 子集对齐的 v1 缓存
# ============================================================

def _load_company(companies: dict, code: str):
    for key, info in companies.items():
        if key.startswith(code):
            return key, info
    raise SystemExit(f"找不到公司 {code}")


def _select_best_v1(stem: str, structured_pages: set[int], expected_count: int):
    """从 v1 content_list 里挑出与 structured 子集对齐的那份，返回 (pdf_page->[html...])。"""
    cache_dir = MINERU_CACHE_DIR / stem
    v1_files = sorted(cache_dir.glob("*_content_list.json"))
    v1_files = [f for f in v1_files if not f.name.endswith("_v2.json")]
    if not v1_files:
        return None

    sp = sorted(structured_pages)
    candidates = []
    for f in v1_files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cl = _normalize_content_list(raw)
        if len(cl) > len(sp):
            continue  # 不同子集（如 rag 全量），跳过
        mapped = []  # (pdf_page, table_body)
        for i, page_elems in enumerate(cl):
            pp = sp[i]
            for e in page_elems:
                if isinstance(e, dict) and e.get("type") == "table":
                    body = e.get("table_body") or e.get("html") or ""
                    mapped.append((pp, body))
        all_in = all(pp in structured_pages for pp, _ in mapped)
        candidates.append((f, mapped, len(mapped), all_in))

    if not candidates:
        return None
    # 打分：优先 all_in，其次表数最接近 expected
    def score(c):
        _, _, cnt, all_in = c
        return (1 if all_in else 0, -abs(cnt - expected_count))

    best = max(candidates, key=score)
    _, mapped, _, _ = best
    # 按 pdf_page 分组，保留顺序
    by_page: dict[int, list[str]] = {}
    for pp, body in mapped:
        by_page.setdefault(pp, []).append(body)
    return by_page


# ============================================================
# 2. 注入 html + 重建
# ============================================================

def _inject_html(existing_tables: list[dict], cache_by_page: dict[int, list[str]]):
    """把缓存 html 按 (page_start, 页内顺序) 注入现有表，返回覆盖率。"""
    # 统计每页现有表数
    page_counts: dict[int, int] = {}
    for t in existing_tables:
        p = int(t.get("page_start") or 0)
        page_counts[p] = page_counts.get(p, 0) + 1

    filled = 0
    for t in existing_tables:
        p = int(t.get("page_start") or 0)
        bodies = cache_by_page.get(p)
        if not bodies:
            continue
        # 该页内第几个（基于文档顺序）
        idx_in_page = sum(
            1 for x in existing_tables[: existing_tables.index(t) + 1]
            if int(x.get("page_start") or 0) == p
        ) - 1
        if 0 <= idx_in_page < len(bodies) and bodies[idx_in_page].strip():
            t["table_html"] = bodies[idx_in_page]
            filled += 1
    return filled


# ============================================================
# 3. 本地 pdfplumber 跨页修复（Method B，零 MinerU）
# ============================================================

def _grid_to_html(grid: list[list]) -> str:
    rows = []
    for r in grid:
        cells = "".join(f"<td>{(c or '').strip()}</td>" for c in r)
        rows.append(f"<tr>{cells}</tr>")
    return "<table>" + "".join(rows) + "</table>"


def _html_to_md(html: str) -> str:
    import re
    text = re.sub(r"</tr>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</t[dh]>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def repair_with_pdfplumber(pdf_path: Path, check, max_merge: int = 3):
    """本地 pdfplumber 抽取（零 API）：跨页拼接所有表行再拼接成一张大表。

    策略：对截断表所在页及其后续续页，逐页 extract_tables，取最大表，
    把所有页的表行纵向拼接成一个大 grid → 重建 html。这样跨页截断的
    汇总行（如"负债和所有者权益总计"）会随续页一起被拼进来。
    """
    try:
        import pdfplumber
    except Exception:
        return None
    pages = list(range(check.page_start, check.page_start + max_merge))
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            all_rows: list[list] = []
            ncols = 0
            for pno in pages:
                if pno - 1 >= len(pdf.pages):
                    break
                page = pdf.pages[pno - 1]
                tables = page.extract_tables()
                if not tables:
                    continue
                grid = max(tables, key=lambda t: len(t) if t else 0)
                for row in grid:
                    all_rows.append(row)
                    ncols = max(ncols, len(row))
            if not all_rows or ncols == 0:
                return None
            norm = [r + [""] * (ncols - len(r)) for r in all_rows]
            return _grid_to_html(norm)
    except Exception:
        return None


# ============================================================
# 4. 读取 metrics.db 旧记录
# ============================================================

def _load_old_records(db_path: Path, company_code: str, skip_notes: bool):
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        "SELECT metric_label, time_scope, period_end, statement_type, source_section, value "
        "FROM metric_records WHERE company_code=?",
        (company_code,),
    )
    rows = cur.fetchall()
    con.close()
    out = []
    for label, ts, pe, st, sec, val in rows:
        if skip_notes and sec == "notes":
            continue
        out.append((label, ts, pe, st, val))
    return out


# ============================================================
# 5. 主流程
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-code", default="600519")
    args = ap.parse_args()
    code = args.company_code

    settings = load_settings()
    db_path = settings.structured_data.sqlite_path
    aliases_path = settings.structured_data.aliases_path

    # 备份 metrics.db（只读试点，但以防万一）
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"metrics_{code}.db"
    shutil.copy(db_path, backup_path)
    print(f"[备份] metrics.db -> {backup_path}")

    # 公司信息
    pf = json.loads(PAGE_FILTER_JSON.read_text(encoding="utf-8"))
    docs = pf["documents"]
    company_key, info = _load_company(docs, code)
    pdf_path = REPO_ROOT / info["pdf_path"]
    sr = [r for r in info["kept_ranges"] if r.get("processing_type") == "structured"]
    structured_pages = set()
    for r in sr:
        structured_pages.update(range(r["start"], r["end"] + 1))
    stem = pdf_path.stem

    # 现有产物
    pdir = (
        settings.retrieval.parsed_filings_root
        / f"{company_key}__annual__2025__{stem}__structured"
    )
    tables_path = pdir / "tables.jsonl"
    elements_path = pdir / "elements.jsonl"
    existing = [json.loads(l) for l in tables_path.open(encoding="utf-8") if l.strip()]
    expected = len(existing)
    print(f"\n[公司] {company_key} | structured 页 {len(structured_pages)} | 现有表 {expected}")

    # 1) 选 v1 缓存并注入 html
    cache_by_page = _select_best_v1(stem, structured_pages, expected)
    if not cache_by_page:
        print("[错误] 未找到对齐的 v1 缓存，无法零成本重建")
        return 1
    filled = _inject_html(existing, cache_by_page)
    print(f"[重建] 注入 html 覆盖率: {filled}/{expected} ({filled/expected*100:.1f}%)")

    # 2) 旧路线截断表数量（markdown）
    old_trunc = find_truncated_tables(existing)
    print(f"[旧路线] 跨页截断表(需 MinerU 修复): {len(old_trunc)}")

    # 3) 重建后截断表数量（html）
    new_trunc = find_truncated_tables(existing)  # existing 已被注入 html
    print(f"[重建后] 跨页截断表: {len(new_trunc)}")

    # 4) 写临时目录 + elements.jsonl，跑提取器（llm_client=None → 跳过注释表，零成本）
    tmp = Path(tempfile.mkdtemp(prefix="pilot_rebuild_"))
    rebuilt_path = tmp / "tables.jsonl"
    rebuilt_path.write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in existing) + "\n",
        encoding="utf-8",
    )
    if elements_path.exists():
        shutil.copy(elements_path, tmp / "elements.jsonl")

    normalizer = MetricNormalizer(aliases_path=aliases_path)
    extractor = TableExtractor(
        company_code=code,
        company_name=info.get("company_name") or company_key.split("_", 1)[-1],
        source_document_id=f"{company_key}__annual__2025__{stem}__structured",
        normalizer=normalizer,
        llm_client=None,  # 跳过注释表，零 LLM 成本
    )
    new_records = extractor.extract_from_tables_file(rebuilt_path)
    print(f"[重建] HTML-first 提取 metric_records: {len(new_records)}")

    # 5) 对比 metrics.db 旧值（仅主表，排除 notes，公平对比）
    old_records = _load_old_records(db_path, code, skip_notes=True)
    print(f"[旧值] metrics.db 主表记录(排除notes): {len(old_records)}")

    # ---- 值级比对（忽略 key schema 漂移，直接比数值）----
    def fval(v):
        try:
            return round(float(str(v).replace(",", "").replace("，", "").strip()), 2)
        except Exception:
            return None

    old_by_label: dict[str, set] = defaultdict(set)
    for r in old_records:
        fv = fval(r[4])
        if fv is not None:
            old_by_label[r[0]].add(fv)
    new_by_label: dict[str, set] = defaultdict(set)
    for r in new_records:
        fv = fval(r.value)
        if fv is not None:
            new_by_label[r.metric_label].add(fv)

    common_labels = set(old_by_label) & set(new_by_label)
    label_recall = []
    mismatch_examples = []
    for lbl in sorted(common_labels):
        ov, nv = old_by_label[lbl], new_by_label[lbl]
        if not ov:
            continue
        rec = len(ov & nv) / len(ov)
        label_recall.append(rec)
        if ov != nv:
            mismatch_examples.append((lbl, sorted(ov - nv), sorted(nv - ov)))

    mean_recall = sum(label_recall) / len(label_recall) * 100 if label_recall else 0
    equal_labels = sum(1 for lbl in common_labels if old_by_label[lbl] == new_by_label[lbl])

    # 诊断：打印几个关键 label 的完整新旧 key，定位 schema 漂移
    print("\n[诊断] 关键 label 完整 key（label | time_scope | period_end | statement_type）")
    for lbl in ["资产总计", "营业收入", "净利润", "经营活动产生的现金流量净额"]:
        ok = [k for k in {(r[0], r[1], r[2], r[3]) for r in old_records} if k[0] == lbl][:2]
        nk = [k for k in {(r.metric_label, r.time_scope, r.period_end, r.statement_type) for r in new_records} if k[0] == lbl][:2]
        for k in ok:
            print(f"    旧 {lbl}: ts={k[1]} pe={k[2]} st={k[3]}")
        for k in nk:
            print(f"    新 {lbl}: ts={k[1]} pe={k[2]} st={k[3]}")

    print("\n========== 对比报告（主表值级比对，排除 notes）==========")
    print(f"  旧路线记录数 : {len(old_records)}")
    print(f"  重建后记录数 : {len(new_records)}")
    print(f"  共有 label   : {len(common_labels)}")
    print(f"  值完全一致 label 数: {equal_labels}/{len(common_labels)}")
    print(f"  旧值召回率(mean label recall): {mean_recall:.1f}%")
    print(f"  值有差异的 label 数: {len(mismatch_examples)}")

    # 关键指标取样（用官方口径呈现）
    print("\n--- 关键指标 旧 vs 新（数值）---")
    for lbl in ["资产总计", "负债和所有者权益总计", "营业收入", "净利润",
                "基本每股收益", "经营活动产生的现金流量净额", "归属于母公司所有者的净利润"]:
        ov = sorted(old_by_label.get(lbl, set()))
        nv = sorted(new_by_label.get(lbl, set()))
        if ov or nv:
            print(f"  {lbl}:")
            print(f"    旧: {[f'{v:,.2f}' for v in ov]}")
            print(f"    新: {[f'{v:,.2f}' for v in nv]}")

    if mismatch_examples[:6]:
        print("\n--- 值差异 label 样例（前 6，旧有\\新有）---")
        for lbl, oonly, nonly in mismatch_examples[:6]:
            print(f"  {lbl}: 旧独有={[f'{v:,.2f}' for v in oonly]} | 新独有={[f'{v:,.2f}' for v in nonly]}")

    # 6) 残留截断表的本地兜底修复成本（A 缝合 / B pdfplumber）
    print("\n========== 残留截断表 本地兜底修复成本 ==========")
    a_ok = b_ok = 0
    remaining = []
    for idx, chk in new_trunc:
        # Method B: pdfplumber 本地
        html = repair_with_pdfplumber(pdf_path, chk)
        if html:
            md = _html_to_md(html)
            chk2 = check_table_completeness(
                table_index=idx, table_markdown=md, page_start=chk.page_start
            )
            if chk2.is_complete:
                b_ok += 1
                continue
        remaining.append((idx, chk))
    print(f"  pdfplumber 本地修复成功: {b_ok}/{len(new_trunc)}")
    print(f"  仍需升级(MinerU)的表 : {len(remaining)}")
    for idx, chk in remaining:
        print(f"    - p{chk.page_start} {chk.table_type} 缺: {chk.missing_rows}")

    # 汇总写入报告
    report = {
        "company_code": code,
        "company_key": company_key,
        "expected_tables": expected,
        "html_injected": filled,
        "html_coverage_pct": round(filled / expected * 100, 1) if expected else 0,
        "old_truncated": len(old_trunc),
        "new_truncated": len(new_trunc),
        "old_records_main": len(old_records),
        "new_records_main": len(new_records),
        "common_labels": len(common_labels),
        "equal_value_labels": equal_labels,
        "mean_label_recall_pct": round(mean_recall, 1),
        "labels_with_diff": len(mismatch_examples),
        "pdfplumber_fixed": b_ok,
        "still_needs_mineru": len(remaining),
        "metrics_db_backup": str(backup_path),
    }
    report_path = BACKUP_DIR / f"report_{code}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[报告] 已写入 {report_path}")
    print("[说明] 本试点只读 metrics.db、未写库、未调 MinerU，可安全复核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
