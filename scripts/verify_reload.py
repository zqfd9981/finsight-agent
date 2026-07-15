"""全量重跑后验证：对比重跑前后快照，统计行数变化、脏数据残留、英文键占比。

用法：
    python scripts/verify_reload.py
依赖：var/data/_rebuild_backup/snapshot_before_reload.json（重跑前由脚本生成）
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB = REPO_ROOT / "var" / "data" / "structured_data" / "metrics.db"
SNAP = REPO_ROOT / "var" / "data" / "_rebuild_backup" / "snapshot_before_reload.json"


def is_english(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z_]+", s or ""))


def main() -> int:
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    before = snap["before_per_company_rows"]
    before_total = snap["before_total_rows"]
    before_dirty = {d["company"]: d for d in snap["dirty_rows"]}

    db = sqlite3.connect(str(DB))
    cur = db.cursor()

    cur.execute("SELECT company_name, COUNT(*) FROM metric_records GROUP BY company_name ORDER BY company_name")
    after = OrderedDict((n, c) for n, c in cur.fetchall())
    after_total = sum(after.values())

    cur.execute("SELECT metric_name FROM metric_records")
    names = [r[0] for r in cur.fetchall()]
    eng = sum(1 for n in names if is_english(n))
    eng_pct = round(eng / len(names) * 100, 2) if names else 0.0

    # 重跑后残留脏数据（同口径）
    cur.execute("""SELECT company_name, metric_label, metric_name, value, unit, source_section
                   FROM metric_records
                   WHERE metric_name LIKE '一、%' OR metric_name LIKE '二、%' OR metric_name LIKE '三、%'
                      OR metric_name LIKE '（%' OR metric_name LIKE '(1%' OR metric_name LIKE '1.%'
                      OR metric_name GLOB '(-*,*' OR metric_name GLOB '(*,*'""")
    after_dirty = [dict(zip(["company", "label", "name", "value", "unit", "section"], r))
                   for r in cur.fetchall()]
    db.close()

    # 行数变化
    all_companies = sorted(set(before) | set(after))
    deltas = []
    for c in all_companies:
        b = before.get(c, 0)
        a = after.get(c, 0)
        if b != a:
            deltas.append((c, b, a, a - b))
    deltas.sort(key=lambda x: x[3])

    print("=" * 64)
    print("全量重跑后验证报告")
    print("=" * 64)
    print(f"公司数: 重跑前 {len(before)} -> 重跑后 {len(after)}")
    print(f"总行数: 重跑前 {before_total} -> 重跑后 {after_total} "
          f"(Δ{after_total - before_total:+d})")
    print(f"metric_name 英文键占比: 重跑前 {snap['metric_name_english_pct_before']}% -> "
          f"重跑后 {eng_pct}%")
    print(f"脏数据行数: 重跑前 {snap['dirty_rows_count']} -> 重跑后 {len(after_dirty)}")

    print("\n--- 行数变化最大的公司 (top 10 增/减) ---")
    for c, b, a, d in (deltas[:5] + deltas[-5:]) if len(deltas) > 10 else deltas:
        print(f"  {c:12} {b:6} -> {a:6}  (Δ{d:+d})")

    print("\n--- 重跑后残留脏数据 ---")
    if not after_dirty:
        print("  (无)")
    else:
        for d in after_dirty:
            print(f"  [{d['company']}] {d['section']:18} name={d['name']!r} val={d['value']!r}")

    # 哪些重跑前脏公司被净化了
    cleaned = [c for c in before_dirty if c not in {d["company"] for d in after_dirty}]
    print("\n--- 被净化的旧脏数据公司 ---")
    print(f"  {cleaned if cleaned else '(无)'}")

    report = {
        "before_total": before_total,
        "after_total": after_total,
        "before_companies": len(before),
        "after_companies": len(after),
        "english_pct_before": snap["metric_name_english_pct_before"],
        "english_pct_after": eng_pct,
        "dirty_before": snap["dirty_rows_count"],
        "dirty_after": len(after_dirty),
        "cleaned_companies": cleaned,
        "residual_dirty": after_dirty,
        "row_deltas": [{"company": c, "before": b, "after": a, "delta": d} for c, b, a, d in deltas],
    }
    out = REPO_ROOT / "var" / "data" / "_rebuild_backup" / "verify_reload_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[报告] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
