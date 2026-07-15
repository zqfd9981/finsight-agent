"""从 MinerU v1 缓存零成本重建结构化指标（HTML 优先路线）并整公司重载。

背景：
  - 88 家已入库公司的 tables.jsonl 是"旧 markdown 路线"产物（table_html 全为空），
    由早期版本 table_extractor 写入 metrics.db，key schema 已过时
    （time_scope 存原始表头如"2024 年 12 月 31 日"、statement_type 全 unknown）。
  - MinerU v1 缓存的 content_list 仍保留 table_body(html)，可直接重建带 html 的
    ParsedDocumentArtifact，**无需重烧 MinerU API**。
  - 现行 table_extractor 已正确归一化 time_scope / statement_type（elements.jsonl 页码映射）。

做法（完全复用生产流水线，仅把 MinerU API 解析替换为读缓存）：
  1. 从 v1 缓存取对齐的 content_list（table_body 含 HTML）
  2. _build_artifact → ParsedDocumentArtifact（table_html 已填，且无旧 cross_page_repair 孤儿残片）
  3. write_parsed_artifact → 重写结构化 pdir 的 tables.jsonl / elements.jsonl
  4. TableExtractor.extract_from_tables_file → metric_records（llm_client=None 跳过注释表，$0）
  5. MetricRepository.save_records_for_company → 按 company_name 整公司删除旧记录再插入（重载）

安全约束：
  - 运行前自动备份 metrics.db 到 var/data/_rebuild_backup/。
  - --dry-run：只扫描 88 家，报告缓存可用性 + HTML 覆盖率，不写 metrics.db（但会重写
    结构化 pdir 的 tables.jsonl/elements.jsonl 并提取，以便报告真实记录数）。
  - 零成本模式（默认，llm_client=None）跳过注释表提取；重载时把旧库 notes 记录
    并入后再整公司保存，避免整公司删除把旧 notes 一起清掉（仅比亚迪/用友网络旧库含 notes）。
  - 仅当某公司提取出非空记录时才调用 save（避免清空旧数据）。

用法：
    python scripts/rebuild_from_cache.py --dry-run
    python scripts/rebuild_from_cache.py --company-code 600519
    python scripts/rebuild_from_cache.py --with-notes        # 启用 LLM 注释表决策（非$0）
    python scripts/rebuild_from_cache.py                      # 全量 88 家零成本重载
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _c in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(_c) not in sys.path:
        sys.path.insert(0, str(_c))

from finsight_agent.config.settings import load_settings  # noqa: E402
from finsight_agent.capabilities.retrieval.parsed_storage import (  # noqa: E402
    write_parsed_artifact,
)
from finsight_agent.capabilities.structured_data.cross_page_repair import (  # noqa: E402
    find_truncated_tables,
)
from finsight_agent.capabilities.structured_data.metric_normalizer import (  # noqa: E402
    MetricNormalizer,
)
from finsight_agent.capabilities.structured_data.models import MetricRecord  # noqa: E402
from finsight_agent.capabilities.structured_data.repository import MetricRepository  # noqa: E402
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor  # noqa: E402
from finsight_agent.infra.document_parsers.mineru_parser import (  # noqa: E402
    _build_artifact,
    _normalize_content_list,
)

PAGE_FILTER_JSON = REPO_ROOT / "var" / "data" / "page_filter" / "annual_2025_pages.json"
MINERU_CACHE_DIR = REPO_ROOT / "var" / "data" / "_mineru_cache"
BACKUP_DIR = REPO_ROOT / "var" / "data" / "_rebuild_backup"


def _load_structured_pages(doc_info: dict) -> set[int]:
    sp: set[int] = set()
    for r in doc_info.get("kept_ranges", []):
        if r.get("processing_type") == "structured":
            sp.update(range(r["start"], r["end"] + 1))
    return sp


def _find_aligned_v1(stem: str, structured_pages: set[int]):
    """从 v1 缓存里挑出与 structured 子集对齐的那份 content_list。

    返回 (content_list_normalized, diagnostics_dict) 或 (None, diagnostics)。
    对齐规则：缓存第 i 页(1-based) → sorted(structured_pages)[i-1]。
    优先选 len(cl)==len(sp) 的精确匹配；其次选首 len(sp) 页可对齐且 HTML 覆盖率达标的。
    """
    cache_dir = MINERU_CACHE_DIR / stem
    if not cache_dir.exists():
        return None, {"error": "no_cache_dir"}
    v1_files = sorted(cache_dir.glob("*_content_list.json"))
    v1_files = [f for f in v1_files if not f.name.endswith("_v2.json")]
    if not v1_files:
        return None, {"error": "no_v1_cache"}

    sp = sorted(structured_pages)
    n_sp = len(sp)
    candidates = []
    for f in v1_files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cl = _normalize_content_list(raw)
        if not cl:
            continue
        # 取前 n_sp 页用于对齐（多余页视为 buffer/rag，交给 _build_artifact 丢弃）
        aligned_pages = cl[:n_sp]
        # 统计 HTML 覆盖率（前 n_sp 页的表，非空 table_body 比例）
        total_tbl = 0
        html_tbl = 0
        for page_elems in aligned_pages:
            for e in page_elems:
                if isinstance(e, dict) and e.get("type") == "table":
                    total_tbl += 1
                    body = e.get("table_body") or e.get("html") or ""
                    if body.strip():
                        html_tbl += 1
        coverage = html_tbl / total_tbl if total_tbl else 0.0
        candidates.append({
            "file": f.name,
            "n_pages": len(cl),
            "aligned_tbl": total_tbl,
            "html_tbl": html_tbl,
            "coverage": coverage,
            "exact": len(cl) == n_sp,
            "content_list": cl,
        })

    if not candidates:
        return None, {"error": "no_usable_cache"}

    # 打分：精确匹配优先；其次覆盖率最高
    def score(c):
        return (1 if c["exact"] else 0, c["coverage"])

    best = max(candidates, key=score)
    diag = {
        "file": best["file"],
        "n_pages": best["n_pages"],
        "exact": best["exact"],
        "aligned_tbl": best["aligned_tbl"],
        "html_tbl": best["html_tbl"],
        "coverage": round(best["coverage"] * 100, 1),
        "n_candidates": len(candidates),
    }
    # 覆盖率过低视为不可用
    if best["coverage"] < 0.4:
        return None, {**diag, "error": "low_coverage"}
    return best["content_list"], diag


def _rebuild_one(
    *,
    company_key: str,
    doc_info: dict,
    settings,
    normalizer: MetricNormalizer,
    llm_client=None,
):
    """重建单家公司：缓存 → artifact → 写 pdir → 提取 → 返回 (records, stats)。

    不写 metrics.db（由调用方统一串行写，避免并发）。
    """
    pdf_path = REPO_ROOT / doc_info["pdf_path"]
    if not pdf_path.exists():
        return [], {"status": "skip", "reason": "pdf_not_found"}

    stem = pdf_path.stem
    structured_pages = _load_structured_pages(doc_info)
    if not structured_pages:
        return [], {"status": "skip", "reason": "no_structured_pages"}

    content_list, diag = _find_aligned_v1(stem, structured_pages)
    if content_list is None:
        return [], {"status": "skip", "reason": diag.get("error", "no_cache"), "diag": diag}

    # 构造 artifact（零 MinerU；page_filter 仅用于页码映射）
    artifact = _build_artifact(
        pdf_path=pdf_path,
        content_list=content_list,
        full_md="",
        page_filter=structured_pages,
    )
    document_id = f"{company_key}__annual__2025__{stem}"
    structured_doc_id = f"{document_id}__structured"
    artifact.document["document_id"] = structured_doc_id

    parsed_root = settings.retrieval.parsed_filings_root
    pdir = write_parsed_artifact(parsed_root, artifact)  # 重写 tables.jsonl/elements.jsonl

    tables_jsonl = pdir / "tables.jsonl"
    n_tables = len([1 for _ in tables_jsonl.open(encoding="utf-8") if _.strip()])

    # 跨页截断统计（重建后）
    raw_tables = [json.loads(l) for l in tables_jsonl.open(encoding="utf-8") if l.strip()]
    truncated = find_truncated_tables(raw_tables)

    company_code = company_key.split("_")[0] if "_" in company_key else ""
    company_name = company_key.split("_", 1)[-1] if "_" in company_key else company_key
    extractor = TableExtractor(
        company_code=company_code,
        company_name=company_name,
        source_document_id=structured_doc_id,
        normalizer=normalizer,
        llm_client=llm_client,
    )
    records = extractor.extract_from_tables_file(tables_jsonl)

    stats = {
        "status": "ok",
        "company_code": company_code,
        "company_name": company_name,
        "structured_pages": len(structured_pages),
        "cache_file": diag.get("file"),
        "html_coverage_pct": diag.get("coverage"),
        "n_tables_written": n_tables,
        "n_records": len(records),
        "n_truncated": len(truncated),
        "truncated": [
            {"page_start": c.page_start, "table_type": c.table_type, "missing": c.missing_rows}
            for _, c in truncated
        ],
        "pdir": str(pdir),
    }
    return records, stats


def _load_old_notes(db_path: Path, company_name: str) -> list:
    """读取某公司旧的 notes 区记录（零成本重建会跳过 notes，需保留以免丢数据）。"""
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute(
            "SELECT company_name, company_code, metric_name, metric_label, time_scope, "
            "period_end, value, unit, currency, source_type, source_document_id, "
            "source_table_id, source_caption, confidence, statement_type, source_section "
            "FROM metric_records WHERE company_name=? AND source_section='notes'",
            (company_name,),
        )
        rows = cur.fetchall()
        con.close()
    except Exception:
        return []
    return [
        MetricRecord(
            company_name=r[0], company_code=r[1], metric_name=r[2], metric_label=r[3],
            time_scope=r[4], period_end=r[5], value=r[6], unit=r[7], currency=r[8],
            source_type=r[9], source_document_id=r[10], source_table_id=r[11],
            source_caption=r[12], confidence=r[13],
            statement_type=r[14] if len(r) > 14 else "unknown",
            source_section=r[15] if len(r) > 15 else "unknown",
        )
        for r in rows
    ]


def _dedup_records(records: list) -> list:
    """按自然键去重（同一指标单元格仅保留首条），幂等且安全。

    自然键：company_name | metric_name | time_scope | period_end | value |
           source_table_id | source_section | statement_type
    修复：零成本模式下注释表仍会被 rule 回退提取（source_section='notes'），
    若再额外并入旧库 notes 会导致 notes 翻倍；此处去重即可同时消除
    提取器自身的重复行（如权益变动表）与 notes 并入带来的重复。
    """
    seen: set = set()
    out: list = []
    for r in records:
        key = (
            getattr(r, "company_name", ""),
            getattr(r, "metric_name", ""),
            getattr(r, "time_scope", ""),
            getattr(r, "period_end", ""),
            getattr(r, "value", ""),
            getattr(r, "source_table_id", ""),
            getattr(r, "source_section", ""),
            getattr(r, "statement_type", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


_WORKER_STATE = {}


def _worker_rebuild(company_key: str, doc_info: dict, with_notes: bool = False):
    """ProcessPoolExecutor 工作进程：每进程仅加载一次 settings/normalizer/llm。

    返回 (company_key, records, stats)，与 _rebuild_one 语义一致；
    抽取阶段的异常在此捕获为 status='error'，避免单家公司拖垮整个进程池。
    """
    st = _WORKER_STATE.get("st")
    if st is None:
        settings = load_settings()
        normalizer = MetricNormalizer(aliases_path=settings.structured_data.aliases_path)
        llm_client = None
        if with_notes:
            try:
                from finsight_agent.infra.llm.client import LlmClient
                llm_client = LlmClient(timeout_seconds=90, max_tokens=8192)
            except Exception:
                llm_client = None
        _WORKER_STATE["st"] = (settings, normalizer, llm_client)
    settings, normalizer, llm_client = _WORKER_STATE["st"]
    try:
        records, stats = _rebuild_one(
            company_key=company_key, doc_info=doc_info,
            settings=settings, normalizer=normalizer, llm_client=llm_client,
        )
    except Exception as exc:
        return company_key, [], {"company_key": company_key, "status": "error",
                                 "reason": f"{type(exc).__name__}: {exc}"}
    return company_key, records, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="从 v1 缓存零成本重建结构化指标并整公司重载")
    ap.add_argument("--company-code", action="append", dest="company_codes", default=None,
                    help="只处理指定公司（可重复，支持逗号分隔）")
    ap.add_argument("--dry-run", action="store_true", help="只扫描报告，不写库/不写 pdir")
    ap.add_argument("--with-notes", action="store_true",
                    help="启用 LLM 注释表 keep/skip 决策与回退提取（非$0，需 AGICTO_API_KEY）")
    ap.add_argument("--workers", type=int, default=min(os.cpu_count() or 4, 8),
                    help="并发抽取进程数（>1 时并行解析 HTML，落库仍串行）；默认 min(cpu,8)")
    args = ap.parse_args()

    settings = load_settings()
    pf = json.loads(PAGE_FILTER_JSON.read_text(encoding="utf-8"))
    documents = pf.get("documents", {})

    flat_codes: list[str] = []
    if args.company_codes:
        for c in args.company_codes:
            flat_codes.extend([s.strip() for s in c.split(",") if s.strip()])

    todo: list[tuple[str, dict]] = []
    for company_key, doc_info in documents.items():
        if doc_info.get("source") in ("failed", "skipped_too_short", "error"):
            continue
        if not doc_info.get("kept_pages"):
            continue
        if flat_codes and not any(code in company_key for code in flat_codes):
            continue
        todo.append((company_key, doc_info))

    print(f"待处理公司: {len(todo)}")
    if args.dry_run:
        print("=== DRY RUN：仅扫描缓存可用性 + HTML 覆盖率，不写库 ===")

    # 归一化器
    aliases_path = settings.structured_data.aliases_path
    normalizer = MetricNormalizer(aliases_path=aliases_path)

    llm_client = None
    if args.with_notes:
        try:
            from finsight_agent.infra.llm.client import LlmClient
            llm_client = LlmClient(timeout_seconds=90, max_tokens=8192)
            print("[notes] 已启用 LLM 注释表决策")
        except Exception as exc:
            print(f"[notes] LLM 初始化失败，回退 $0 模式: {exc}")
            llm_client = None

    t0 = time.time()

    # ---- Phase A: 抽取（可并发；落库在 Phase B 串行，避免 SQLite 写锁冲突） ----
    use_pool = (args.workers or 1) > 1 and len(todo) > 1
    extracted: list[tuple] = []  # (company_key, records, stats)
    if use_pool:
        print(f"[并发] 使用 {args.workers} 个进程并行抽取 {len(todo)} 家公司...", flush=True)
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(_worker_rebuild, ck, di, args.with_notes): ck for ck, di in todo}
            for fut in as_completed(futs):
                ck, recs, st = fut.result()
                extracted.append((ck, recs, st))
                if st.get("status") == "error":
                    print(f"  [ERR] {ck}: {st.get('reason')}", flush=True)
    else:
        for company_key, doc_info in todo:
            try:
                recs, st = _rebuild_one(
                    company_key=company_key, doc_info=doc_info,
                    settings=settings, normalizer=normalizer, llm_client=llm_client,
                )
            except Exception as exc:
                st = {"company_key": company_key, "status": "error",
                      "reason": f"{type(exc).__name__}: {exc}"}
                recs = []
                print(f"  [ERR] {company_key}: {type(exc).__name__}: {exc}", flush=True)
            extracted.append((company_key, recs, st))

    # ---- Phase B: 下游处理（串行，与单列逻辑完全一致） ----
    all_records: list = []
    results: list[dict] = []
    skipped = 0
    failed = 0

    for company_key, records, stats in extracted:
        if stats.get("status") == "error":
            failed += 1
            results.append(stats)
            continue

        if stats.get("status") == "skip":
            skipped += 1
            results.append({"company_key": company_key, **stats})
            print(f"  [SKIP] {company_key}: {stats.get('reason')}", flush=True)
            continue

        if args.dry_run:
            results.append({"company_key": company_key, **stats})
            print(f"  [DRY ] {company_key}: cache={stats['cache_file']} "
                  f"html覆盖率={stats['html_coverage_pct']}% 表={stats['n_tables_written']} "
                  f"截断={stats['n_truncated']}", flush=True)
            continue

        # 正式落库：仅当提取出非空记录
        if records:
            preserved_notes = 0
            if not args.with_notes:
                # 零成本模式跳过 notes 提取：保留旧库 notes 记录，避免整公司删除时丢失
                try:
                    old_notes = _load_old_notes(settings.structured_data.sqlite_path, stats["company_name"])
                except Exception as exc:
                    print(f"    [警告] {company_key} 读取旧 notes 失败: {exc}", flush=True)
                    old_notes = []
                if old_notes:
                    records = records + old_notes
                    preserved_notes = len(old_notes)
            # 去重（消除提取器自身重复 + notes 并入带来的重复），幂等安全
            records = _dedup_records(records)
            all_records.append((stats["company_name"], records))
            stats["n_records"] = len(records)
            stats["n_old_notes_preserved"] = preserved_notes
            results.append({"company_key": company_key, **stats})
            print(f"  [OK  ] {company_key}: 表={stats['n_tables_written']} "
                  f"记录={stats['n_records']} 保留notes={preserved_notes} 截断={stats['n_truncated']}", flush=True)
        else:
            skipped += 1
            results.append({"company_key": company_key, "status": "skip", "reason": "no_records"})
            print(f"  [SKIP] {company_key}: 提取 0 条，保留旧数据", flush=True)

    # 正式模式：备份 metrics.db 后整公司重载
    if not args.dry_run and all_records:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        db_path = settings.structured_data.sqlite_path
        backup_path = BACKUP_DIR / f"metrics_{time.strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy(db_path, backup_path)
        print(f"\n[备份] metrics.db -> {backup_path}")

        repo = MetricRepository(sqlite_path=db_path)
        total_preserved = 0
        for company_name, records in all_records:
            repo.save_records_for_company(company_name, records)
            total_preserved += sum(1 for r in records if getattr(r, "source_section", "") == "notes")
        print(f"[重载] 已整公司重载 {len(all_records)} 家公司；保留旧 notes 记录 {total_preserved} 条")

    # 汇总报告
    elapsed = time.time() - t0
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    trunc_total = sum(r.get("n_truncated", 0) for r in results if r.get("status") == "ok")
    report = {
        "mode": "dry_run" if args.dry_run else "reload",
        "with_notes": bool(args.with_notes),
        "total_companies": len(todo),
        "ok": ok_count,
        "skipped": skipped,
        "failed": failed,
        "total_records": sum(len(r) for _, r in all_records) if all_records else 0,
        "total_truncated_tables": trunc_total,
        "elapsed_sec": round(elapsed, 1),
        "details": results,
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BACKUP_DIR / "rebuild_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 完成：{ok_count} 成功 / {skipped} 跳过 / {failed} 失败，耗时 {elapsed:.1f}s ===")
    print(f"[报告] {report_path}")
    if not args.dry_run:
        print(f"[说明] metrics.db 已备份；{ok_count} 家公司已用现行 HTML 优先路线整公司重载。"
              f"残留截断表共 {trunc_total} 张，需后续本地修复/MinerU 重解析处理。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
