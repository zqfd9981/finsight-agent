"""一键全流程语料建设脚本：下载 → 解析 → 切块 → 重建索引。

用法：
    # 全量执行（100家，2023-2025）
    python scripts/build_corpus_pipeline.py --manifest var/data/corpus_manifests/csi300_industry_leaders.yaml --start-date 2023-01-01 --end-date 2025-12-31

    # 小范围测试（3家）
    python scripts/build_corpus_pipeline.py --manifest var/data/corpus_manifests/csi300_industry_leaders.yaml --start-date 2023-01-01 --end-date 2025-12-31 --company-count 3

    # 只下载不建索引
    python scripts/build_corpus_pipeline.py --manifest ... --start-date ... --end-date ... --skip-index

    # 只重建索引（已有解析数据）
    python scripts/build_corpus_pipeline.py --manifest ... --start-date ... --end-date ... --skip-download --skip-parse
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.chunking import build_chunks
from finsight_agent.capabilities.retrieval.corpus_manifest import load_sample_universe
from finsight_agent.capabilities.retrieval.parsed_storage import (
    write_chunk_artifact,
    write_parsed_artifact,
)
from finsight_agent.capabilities.retrieval.parsing_service import build_parsing_service
from finsight_agent.capabilities.retrieval.service import (
    build_pdf_corpus_acquisition_service,
    build_retrieval_facade,
)
from finsight_agent.config.settings import load_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键全流程语料建设：下载→解析→切块→重建索引")
    parser.add_argument("--manifest", required=True, help="样本股池 YAML 路径")
    parser.add_argument("--start-date", required=True, help="披露起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="披露结束日期 YYYY-MM-DD")
    parser.add_argument("--company-count", type=int, default=None, help="试点公司数量（默认全部）")
    parser.add_argument("--company-code", action="append", dest="company_codes", default=None, help="只处理指定公司（可重复）")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载步骤")
    parser.add_argument("--skip-parse", action="store_true", help="跳过解析+切块步骤")
    parser.add_argument("--skip-index", action="store_true", help="跳过索引重建步骤")
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="下载阶段的公司级并发数（默认 5）",
    )
    return parser.parse_args(argv)


def _download_one_company(service, company, start_date, end_date) -> dict:
    """单家公司下载任务（供线程池调用）。返回可序列化的结果字典。"""
    company_t0 = time.time()
    try:
        result = service.download_filings(
            companies=[company],
            start_date=start_date,
            end_date=end_date,
            snapshot_name=f"single_{company.company_code}",
        )
        elapsed = time.time() - company_t0
        return {
            "company_code": company.company_code,
            "company_name": company.company_name,
            "downloaded_count": result.downloaded_count,
            "failed_count": result.failed_count,
            "elapsed": elapsed,
            "error": None,
        }
    except Exception as exc:
        elapsed = time.time() - company_t0
        return {
            "company_code": company.company_code,
            "company_name": company.company_name,
            "downloaded_count": 0,
            "failed_count": 0,
            "elapsed": elapsed,
            "error": f"{type(exc).__name__}: {exc}",
        }


def step_download(settings, sample_universe, args) -> dict:
    """Step 1: 并行下载 PDF（公司级并发），打印每家进度。"""
    print("\n" + "=" * 60)
    print("[Step 1/3] 下载 PDF 语料（并行）")
    print("=" * 60, flush=True)

    service = build_pdf_corpus_acquisition_service()
    company_count = args.company_count or len(sample_universe.companies)
    selected_companies = sample_universe.select_companies(
        limit=company_count,
        company_codes=args.company_codes,
    )
    total = len(selected_companies)
    workers = max(1, args.workers)
    print(f"  待下载公司: {total} 家, 并发数: {workers}", flush=True)

    total_downloaded = 0
    total_failed = 0
    completed = 0
    t0 = time.time()
    print_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_company = {
            executor.submit(
                _download_one_company,
                service,
                company,
                args.start_date,
                args.end_date,
            ): company
            for company in selected_companies
        }
        for future in as_completed(future_to_company):
            res = future.result()
            completed += 1
            total_downloaded += res["downloaded_count"]
            total_failed += res["failed_count"]
            with print_lock:
                if res["error"] is not None:
                    print(
                        f"  [{completed}/{total}] {res['company_code']} {res['company_name']} "
                        f"FAIL: {res['error']} ({res['elapsed']:.1f}s)",
                        flush=True,
                    )
                else:
                    print(
                        f"  [{completed}/{total}] {res['company_code']} {res['company_name']} "
                        f"OK (下载 {res['downloaded_count']}, 失败 {res['failed_count']}, {res['elapsed']:.1f}s)",
                        flush=True,
                    )

    elapsed = time.time() - t0
    summary = {
        "downloaded_count": total_downloaded,
        "failed_count": total_failed,
        "elapsed_seconds": round(elapsed, 1),
        "workers": workers,
    }
    print(
        f"\n  下载完成: 共 {total_downloaded} 份, 失败 {total_failed} 份, "
        f"耗时 {elapsed:.1f}s, 并发 {workers}",
        flush=True,
    )
    return summary


def step_parse_and_chunk(settings) -> dict:
    """Step 2: 批量解析 PDF + 切块。"""
    print("\n" + "=" * 60)
    print("[Step 2/3] 解析 PDF + 切块")
    print("=" * 60)

    parsing_service = build_parsing_service()
    raw_root = settings.retrieval.raw_filings_root
    parsed_root = settings.retrieval.parsed_filings_root
    chunk_root = settings.retrieval.chunked_filings_root

    pdf_files = sorted(raw_root.rglob("*.pdf"))
    print(f"  发现 {len(pdf_files)} 个 PDF 文件待解析")

    # 收集已解析的 document_id，避免重复
    parsed_doc_ids: set[str] = set()
    if parsed_root.exists():
        for manifest_path in parsed_root.rglob("manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                doc_id = str(payload.get("document", {}).get("document_id", ""))
                if doc_id:
                    parsed_doc_ids.add(doc_id)
            except Exception:
                continue

    print(f"  已解析 {len(parsed_doc_ids)} 份，将跳过")

    success_count = 0
    skip_count = 0
    fail_count = 0
    t0 = time.time()

    for i, pdf_path in enumerate(pdf_files, 1):
        # 从路径推断 document_id：raw_filings/<company_code>/<doc_type>/<year>/<filename>
        # document_id 约定为 company_code|doc_type|year|filename_stem
        try:
            rel_path = pdf_path.relative_to(raw_root)
            parts = rel_path.parts
            company_code = parts[0] if len(parts) > 0 else ""
            doc_type = parts[1] if len(parts) > 1 else ""
            year = parts[2] if len(parts) > 2 else ""
            stem = pdf_path.stem
            document_id = f"{company_code}__{doc_type}__{year}__{stem}"
        except Exception:
            document_id = pdf_path.stem

        if document_id in parsed_doc_ids:
            skip_count += 1
            continue

        print(f"  [{i}/{len(pdf_files)}] 解析 {pdf_path.name} ...", end=" ", flush=True)
        try:
            artifact = parsing_service.parse_document(pdf_path)
            # 强制设置 document_id 以匹配路径推断
            artifact.document["document_id"] = document_id

            write_parsed_artifact(parsed_root, artifact)

            parser_version = (
                artifact.parse_report.parser_version
                if artifact.parse_report is not None
                else "unknown"
            )
            chunking_result = build_chunks(
                document_id=document_id,
                elements=artifact.elements,
                parser_version=parser_version,
                parent_target_chars=settings.retrieval.parent_target_chars,
                child_target_chars=settings.retrieval.child_target_chars,
            )
            write_chunk_artifact(
                root=chunk_root,
                document_id=document_id,
                parents=chunking_result.parents,
                children=chunking_result.children,
                chunk_report={
                    "document_id": document_id,
                    "chunker_version": "chunker_v1",
                    "parent_count": len(chunking_result.parents),
                    "child_count": len(chunking_result.children),
                    "warnings": [],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            success_count += 1
            print(f"OK (parents={len(chunking_result.parents)}, children={len(chunking_result.children)})")
        except Exception as exc:
            fail_count += 1
            print(f"FAIL: {type(exc).__name__}: {exc}")

    elapsed = time.time() - t0
    summary = {
        "total_pdf": len(pdf_files),
        "success": success_count,
        "skipped": skip_count,
        "failed": fail_count,
        "elapsed_seconds": round(elapsed, 1),
    }
    print(f"\n  解析完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}, 耗时 {elapsed:.1f}s")
    return summary


def step_rebuild_index(settings) -> dict:
    """Step 3: 重建 sparse + dense 索引。"""
    print("\n" + "=" * 60)
    print("[Step 3/3] 重建检索索引（sparse + dense）")
    print("=" * 60)

    t0 = time.time()
    facade = build_retrieval_facade()

    print("  重建 sparse 索引 (SQLite BM25) ...", end=" ", flush=True)
    sparse_count = facade.sparse_facade.rebuild_index()
    print(f"OK ({sparse_count} chunks)")

    print("  重建 dense 索引 (Qdrant + embedding) ...", end=" ", flush=True)
    dense_count = facade.dense_facade.rebuild_index()
    print(f"OK ({dense_count} chunks)")

    facade.close()
    elapsed = time.time() - t0

    summary = {
        "sparse_indexed": sparse_count,
        "dense_indexed": dense_count,
        "elapsed_seconds": round(elapsed, 1),
    }
    print(f"  索引重建完成: sparse={sparse_count}, dense={dense_count}, 耗时 {elapsed:.1f}s")
    return summary


def run_pipeline(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path
    sample_universe = load_sample_universe(manifest_path)

    print(f"语料建设流水线启动")
    print(f"  Manifest: {manifest_path}")
    print(f"  公司总数: {len(sample_universe.companies)}")
    print(f"  时间范围: {args.start_date} ~ {args.end_date}")
    if args.company_count:
        print(f"  试点数量: {args.company_count}")
    if args.company_codes:
        print(f"  指定公司: {args.company_codes}")

    pipeline_summary: dict = {"steps": {}}

    if not args.skip_download:
        pipeline_summary["steps"]["download"] = step_download(settings, sample_universe, args)

    if not args.skip_parse:
        pipeline_summary["steps"]["parse_and_chunk"] = step_parse_and_chunk(settings)

    if not args.skip_index:
        pipeline_summary["steps"]["rebuild_index"] = step_rebuild_index(settings)

    print("\n" + "=" * 60)
    print("流水线完成")
    print("=" * 60)
    print(json.dumps(pipeline_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pipeline())
