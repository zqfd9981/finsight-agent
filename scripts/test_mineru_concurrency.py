"""测试 MinerU API 并发上限。

策略：同时发起 N 个解析请求（同一 PDF 不同页码区间），观察：
  - 是否触发 429 限流
  - 是否被串行化处理（完成时间是否接近串行）
  - 实际并发度

用法：
    python scripts/test_mineru_concurrency.py --workers 3
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser


def parse_pages(parser: MineruDocumentParser, pdf_path: Path, pages: set[int], tag: str) -> dict:
    """解析指定页码区间，返回统计信息。"""
    start = time.time()
    try:
        artifact = parser.parse(pdf_path, page_filter=pages)
        elapsed = time.time() - start
        return {
            "tag": tag,
            "status": "ok",
            "pages": len(pages),
            "elements": len(artifact.elements),
            "tables": len(artifact.tables),
            "elapsed": elapsed,
        }
    except Exception as exc:
        elapsed = time.time() - start
        return {
            "tag": tag,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": elapsed,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="测试 MinerU API 并发上限")
    parser.add_argument("--workers", type=int, default=3, help="并发数")
    parser.add_argument(
        "--pdf",
        type=str,
        default="var/data/raw_filings/002129_TCL中环/annual/2025/002129_TCL中环_annual_report_2025_20250426.pdf",
        help="测试用 PDF 路径",
    )
    args = parser.parse_args()

    pdf_path = REPO_ROOT / args.pdf
    if not pdf_path.exists():
        print(f"错误：PDF 不存在: {pdf_path}")
        return 1

    # 准备 5 个不同的页码区间（避免 cache 命中）
    # 从 page_filter 里 002129 的 structured 区间取 5 组
    all_tasks = [
        ("task_A_p86_87", {86, 87}),
        ("task_B_p88_89", {88, 89}),
        ("task_C_p90_91", {90, 91}),
        ("task_D_p92_93", {92, 93}),
        ("task_E_p94_95", {94, 95}),
    ]
    tasks = all_tasks[: args.workers]

    print(f"测试并发数: {len(tasks)}")
    print(f"PDF: {pdf_path.name}")
    print(f"每个任务解析 2 页，共 {len(tasks)} 个任务")
    print("=" * 70, flush=True)

    mineru_parser = MineruDocumentParser()

    overall_start = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(parse_pages, mineru_parser, pdf_path, pages, tag): tag
            for tag, pages in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status_icon = "✓" if result["status"] == "ok" else "✗"
            extra = ""
            if result["status"] == "ok":
                extra = f"pages={result['pages']} elements={result['elements']} tables={result['tables']}"
            else:
                extra = result.get("error", "")[:80]
            print(
                f"{status_icon} {result['tag']} | {result['elapsed']:.1f}s | {extra}",
                flush=True,
            )

    total_elapsed = time.time() - overall_start
    print("=" * 70)
    print(f"总耗时: {total_elapsed:.1f}s")

    # 分析
    ok_results = [r for r in results if r["status"] == "ok"]
    failed_results = [r for r in results if r["status"] != "ok"]
    sum_serial = sum(r["elapsed"] for r in ok_results)

    print(f"\n=== 分析 ===")
    print(f"成功: {len(ok_results)} | 失败: {len(failed_results)}")
    print(f"串行总时长（各任务耗时之和）: {sum_serial:.1f}s")
    print(f"并行实际总耗时: {total_elapsed:.1f}s")

    if failed_results:
        has_429 = any("429" in r.get("error", "") for r in failed_results)
        if has_429:
            print(f"\n⚠️  检测到 429 限流！并发数 {args.workers} 超出 MinerU API 限制")
        else:
            print(f"\n⚠️  有失败任务，但非 429 限流：")
            for r in failed_results:
                print(f"  {r['tag']}: {r.get('error', '')[:100]}")

    if ok_results and not failed_results:
        speedup = sum_serial / total_elapsed if total_elapsed > 0 else 0
        print(f"加速比: {speedup:.2f}x（理想值 {args.workers}.0x）")
        if speedup > args.workers * 0.7:
            print(f"\n✅ 并发数 {args.workers} 可行，MinerU API 支持此并发度")
        elif speedup > 1.2:
            print(f"\n⚠️  部分并行化，MinerU API 可能限制了并发度")
        else:
            print(f"\n❌ 无加速效果，MinerU API 可能串行化处理请求")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
