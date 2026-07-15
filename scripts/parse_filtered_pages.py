"""基于 page_filter JSON 只解析筛选后的页面，按 processing_type 分流入库。

策略：
  - RAG 区间：MinerU 解析 → 切块 → 写入 parsed/chunked storage（后续入向量库）
  - Structured 区间：MinerU 解析 → 提取表格 → 写入 MetricRepository（后续支持指标查询）

用法：
    python scripts/parse_filtered_pages.py --company-code 002129
    python scripts/parse_filtered_pages.py --skip-index
    python scripts/parse_filtered_pages.py --force
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.chunking import build_chunks
from finsight_agent.capabilities.retrieval.parsed_storage import (
    write_chunk_artifact,
    write_parsed_artifact,
)
from finsight_agent.capabilities.retrieval.service import build_retrieval_facade
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser
from finsight_agent.infra.document_parsers.pdfplumber_parser import PdfplumberDocumentParser
from finsight_agent.capabilities.structured_data.cross_page_repair import (
    apply_repair_to_tables,
    find_truncated_tables,
    repair_truncated_table,
)
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor

PAGE_FILTER_JSON = REPO_ROOT / "var" / "data" / "page_filter" / "annual_2025_pages.json"
MINERU_CACHE_DIR = REPO_ROOT / "var" / "data" / "_mineru_cache"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按筛选页面解析年报 PDF，分流入库")
    parser.add_argument("--company-code", action="append", dest="company_codes", default=None,
                        help="只处理指定公司目录名（可重复，支持逗号分隔如 000001,000963）")
    parser.add_argument("--skip-index", action="store_true", help="跳过索引重建")
    parser.add_argument("--force", action="store_true", help="强制重新解析（忽略断点续传）")
    parser.add_argument("--use-pdfplumber", action="store_true",
                        help="用 pdfplumber 代替 MinerU（调试用，不支持 structured 分流）")
    parser.add_argument("--build-aliases", action="store_true",
                        help="提取后调 LLM 生成 metric_name 映射表（需 AGICTO_API_KEY）")
    parser.add_argument("--workers", type=int, default=5,
                        help="并行解析的公司数（默认 5，MinerU API 无限流，瓶颈在本地代理）")
    return parser.parse_args(argv)


def build_document_id(pdf_path: Path, raw_root: Path) -> str:
    """从路径推断 document_id。"""
    rel_path = pdf_path.relative_to(raw_root)
    parts = rel_path.parts
    company_dir = parts[0] if len(parts) > 0 else ""
    doc_type = parts[1] if len(parts) > 1 else ""
    year = parts[2] if len(parts) > 2 else ""
    stem = pdf_path.stem
    return f"{company_dir}__{doc_type}__{year}__{stem}"


def load_parsed_doc_ids(parsed_root: Path) -> set[str]:
    """收集已解析的 document_id，支持断点续传。"""
    parsed_doc_ids: set[str] = set()
    if not parsed_root.exists():
        return parsed_doc_ids
    for manifest_path in parsed_root.rglob("manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            doc_id = str(payload.get("document", {}).get("document_id", ""))
            if doc_id:
                parsed_doc_ids.add(doc_id)
        except Exception:
            continue
    return parsed_doc_ids


def split_ranges_by_processing_type(kept_ranges: list[dict]) -> tuple[list[dict], list[dict]]:
    """把 kept_ranges 按 processing_type 分成 rag 和 structured 两组。"""
    rag_ranges: list[dict] = []
    structured_ranges: list[dict] = []
    for r in kept_ranges:
        ptype = r.get("processing_type", "rag")
        if ptype == "structured":
            structured_ranges.append(r)
        else:
            rag_ranges.append(r)
    return rag_ranges, structured_ranges


def ranges_to_pages(ranges: list[dict]) -> set[int]:
    """把区间列表转成页码集合。"""
    pages: set[int] = set()
    for r in ranges:
        pages.update(range(r["start"], r["end"] + 1))
    return pages


def _read_tables_jsonl(path: Path) -> list[dict]:
    """读取 tables.jsonl 返回 list[dict]。"""
    if not path.exists():
        return []
    tables = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tables.append(json.loads(line))
    return tables


# ============================================================
# 反查校准（修复8）：扫 __rag/tables.jsonl 找三表，移到 __structured
# ============================================================

# 三表标题关键词：匹配 section_path[0] 或 caption
STATEMENT_TITLE_KEYWORDS = (
    "资产负债表",
    "利润表",
    "现金流量表",
    "所有者权益变动表",
    "股东权益变动表",
)


def _is_real_financial_statement(table: dict) -> bool:
    """判断一张表是否是真正的三表（资产负债表/利润表/现金流量表/权益变动表）。

    两层判据：
    1. section_path[0] 严格匹配三表标题（去掉"合并/公司/母公司/本行"前缀和"（续）"后缀后等于三表标题）
    2. 若 section_path 不匹配（如平安银行 MinerU 把 section_path 全标错），
       用 table_markdown 内容匹配三表专属科目组合

    排除注释区子表（如"1. 资产负债表日后利润分配""期末已背书...应收票据"）。
    """
    import re

    section_path = table.get("section_path") or []
    first_section = str(section_path[0]).strip() if section_path else ""

    # === 判据1：section_path[0] 严格匹配三表标题 ===
    cleaned = re.sub(r"^(合并|公司|母公司|本行|本公司)", "", first_section)
    cleaned = re.sub(r"（续）$|（续表）$|\(续\)$|\(续表\)$", "", cleaned).strip()
    for kw in STATEMENT_TITLE_KEYWORDS:
        if cleaned == kw:
            return True

    # === 判据2：table_markdown 内容匹配三表专属科目组合 ===
    # 场景：平安银行 MinerU 把 section_path 全标成"2、重大关联交易..."，但 markdown 是三表
    md = table.get("table_markdown", "") or ""
    if not md or len(md) < 50:
        return False

    # 三表格式特征：必须有"附注"列（"项目 | 附注 | 日期"或"附注四 | 本集团"）
    # MD&A 摘要表没有"附注"列
    has_note_column = "附注" in md[:200]  # 只看表头前200字符

    # 资产负债表专属科目组合（同时含2个以上）
    BS_METRICS = ("资产总计", "负债合计", "所有者权益合计", "股东权益合计",
                  "现金及存放中央银行款项", "存放同业款项")
    # 利润表专属科目组合（含"其他综合收益"以识别 IS 续表）
    IS_METRICS = ("营业支出", "利润总额", "所得税费用", "利息支出",
                  "手续费及佣金收入", "营业总成本", "其他综合收益的税后净额")
    # 现金流量表专属科目组合
    CF_METRICS = ("经营活动产生的现金流量", "投资活动产生的现金流量",
                  "筹资活动产生的现金流量", "现金及现金等价物净增加额")
    # 权益变动表专属特征：含"股本""资本公积""盈余公积"等权益类科目 + 余额行
    EQ_METRICS = ("股本", "资本公积", "盈余公积", "未分配利润", "一般风险准备")

    # 资产负债表：含2个以上 BS 专属科目，且不含注释区特征词
    bs_hits = sum(1 for m in BS_METRICS if m in md)
    if bs_hits >= 2 and not any(x in md for x in ("账龄", "坏账准备", "明细", "前五名")):
        # 进一步确认：含"流动资产""流动负债"或双行表头"附注四 | 本集团"
        if "流动资产" in md or "流动负债" in md or "附注四" in md:
            return True

    # 利润表：含2个以上 IS 专属科目，且必须有"附注"列（排除 MD&A 摘要表）
    is_hits = sum(1 for m in IS_METRICS if m in md)
    if is_hits >= 2 and not any(x in md for x in ("账龄", "坏账准备", "前五名", "明细")):
        # 必须有"附注"列 或 含"一、营业总收入"（合并利润表特有）
        if has_note_column or "一、营业总收入" in md:
            return True
    # IS 续表（其他综合收益部分）：含"其他综合收益的税后净额" + has_note_column
    # 银行股 IS 续表只有这一项，但格式是三表格式（附注四 | 本集团）
    if "其他综合收益的税后净额" in md and has_note_column:
        return True

    # 现金流量表：含2个以上 CF 专属科目，且必须有"附注"列
    # 排除 MD&A 的"5、现金流"摘要（含"经营活动现金流入小计"但无"经营活动产生的现金流量"）
    cf_hits = sum(1 for m in CF_METRICS if m in md)
    if cf_hits >= 2 and has_note_column:
        return True
    # CF 续表（只含一类活动）：含1个 CF 专属科目 + has_note_column + 含"现金流量"关键词
    # 银行股 CF 分活动类型跨页，续表只有"经营活动产生的现金流量"或"投资活动产生的现金流量"
    if cf_hits >= 1 and has_note_column and "现金流量" in md:
        return True

    # 权益变动表：含3个以上 EQ 专属科目 + 余额行特征
    # 平安用"一、2024年1月1日余额"，格力用"一、上年年末余额"，都需覆盖
    import re
    eq_hits = sum(1 for m in EQ_METRICS if m in md)
    if eq_hits >= 3:
        # 排除 MD&A 的权益简表（"年初数""本年增加""本年减少""年末数"是简表格式）
        if any(x in md for x in ("年初数", "本年增加", "本年减少", "年末数")):
            return False
        # 余额行特征：一、上年 / 一、20XX年 / 上年年末 / 本期增减
        if (re.search(r"一、(上年|20\d{2}年)", md) or
            "上年年末" in md or "本期增减" in md or
            "股东权益合计" in md):  # 权益变动表必有"股东权益合计"列
            return True

    return False


def recalibrate_financial_statements(
    rag_tables_path: Path,
    structured_tables_path: Path,
    rag_elements_path: Path | None = None,
    structured_elements_path: Path | None = None,
) -> tuple[list[dict], list[int]]:
    """反查校准：把 __rag 里的三表移到 __structured。

    场景：page_filter LLM 把三表页错配到 rag（如格力 p111-120、平安 p122-139），
    导致 TableExtractor 只读 __structured 读不到三表。

    本函数扫 __rag/tables.jsonl，找真正的三表（section_path[0] 含三表标题），
    把这些表的 JSON 行移到 __structured/tables.jsonl。
    同时把三表页的 elements 从 __rag/elements.jsonl 移到 __structured/elements.jsonl，
    让 TableExtractor 的 _build_statement_type_map 能识别三表标题。

    返回 (移走的表列表, 移走的表所在页码列表)。
    """
    if not rag_tables_path.exists():
        return [], []
    if not structured_tables_path.exists():
        return [], []

    rag_tables = _read_tables_jsonl(rag_tables_path)
    structured_tables = _read_tables_jsonl(structured_tables_path)

    # 找三表
    stmt_tables: list[dict] = []
    remaining_rag: list[dict] = []
    moved_pages: set[int] = set()
    for t in rag_tables:
        if _is_real_financial_statement(t):
            stmt_tables.append(t)
            # 收集表所在页码
            p_start = t.get("page_start")
            p_end = t.get("page_end")
            if p_start and p_end:
                for p in range(p_start, p_end + 1):
                    moved_pages.add(p)
        else:
            remaining_rag.append(t)

    if not stmt_tables:
        return [], []

    # 写回 __rag/tables.jsonl（移除三表）
    with rag_tables_path.open("w", encoding="utf-8") as f:
        for t in remaining_rag:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 追加到 __structured/tables.jsonl
    with structured_tables_path.open("a", encoding="utf-8") as f:
        for t in stmt_tables:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 同步移动 elements：把三表页的 elements 从 __rag 移到 __structured
    # 这是 TableExtractor 的 _build_statement_type_map 能识别三表标题的关键
    if rag_elements_path and structured_elements_path and moved_pages:
        if rag_elements_path.exists() and structured_elements_path.exists():
            remaining_elements: list[str] = []
            moved_elements: list[str] = []
            with rag_elements_path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        el = json.loads(line)
                        el_page = int(el.get("page_start") or 0)
                        if el_page in moved_pages:
                            moved_elements.append(line.rstrip("\n"))
                        else:
                            remaining_elements.append(line.rstrip("\n"))
                    except Exception:
                        remaining_elements.append(line.rstrip("\n"))

            if moved_elements:
                # 写回 __rag/elements.jsonl（移除三表页）
                with rag_elements_path.open("w", encoding="utf-8") as f:
                    for line in remaining_elements:
                        f.write(line + "\n")

                # 追加到 __structured/elements.jsonl
                with structured_elements_path.open("a", encoding="utf-8") as f:
                    for line in moved_elements:
                        f.write(line + "\n")

    return stmt_tables, sorted(moved_pages)


def _apply_repair_to_tables_jsonl(path: Path, raw_tables: list[dict], repair_results: list) -> None:
    """把修复后的 table_markdown 写回 tables.jsonl。"""
    new_tables = apply_repair_to_tables(raw_tables, repair_results)
    with path.open("w", encoding="utf-8") as f:
        for tbl in new_tables:
            f.write(json.dumps(tbl, ensure_ascii=False) + "\n")


def process_company(
    *,
    company_key: str,
    doc_info: dict,
    raw_root: Path,
    parsed_root: Path,
    chunk_root: Path,
    settings,
    mineru_parser: MineruDocumentParser,
    pdfplumber_parser: PdfplumberDocumentParser,
    use_pdfplumber: bool = False,
    normalizer: MetricNormalizer | None = None,
) -> dict:
    """处理单个公司：按 processing_type 分流解析。返回统计信息。"""
    pdf_rel_path = doc_info["pdf_path"]
    pdf_path = REPO_ROOT / pdf_rel_path
    total_pages = doc_info.get("total_pages", 0)

    if not pdf_path.exists():
        return {"status": "skip", "reason": "file_not_found"}

    document_id = build_document_id(pdf_path, raw_root)
    kept_ranges = doc_info.get("kept_ranges", [])
    rag_ranges, structured_ranges = split_ranges_by_processing_type(kept_ranges)

    rag_pages = ranges_to_pages(rag_ranges)
    structured_pages = ranges_to_pages(structured_ranges)

    result = {
        "status": "ok",
        "document_id": document_id,
        "rag_pages": len(rag_pages),
        "structured_pages": len(structured_pages),
        "rag_elements": 0,
        "structured_elements": 0,
        "rag_chunks": 0,
        "rag_tables": 0,
        "structured_tables": 0,
        "structured_metrics": 0,
    }

    # === RAG 路径：解析 → 切块 → 入库 ===
    if rag_pages:
        try:
            if use_pdfplumber:
                artifact = pdfplumber_parser.parse(pdf_path, page_filter=rag_pages)
            else:
                artifact = mineru_parser.parse(pdf_path, page_filter=rag_pages)
            artifact.document["document_id"] = f"{document_id}__rag"
            write_parsed_artifact(parsed_root, artifact)

            parser_version = (
                artifact.parse_report.parser_version
                if artifact.parse_report is not None
                else "unknown"
            )
            chunking_result = build_chunks(
                document_id=f"{document_id}__rag",
                elements=artifact.elements,
                parser_version=parser_version,
                parent_target_chars=settings.retrieval.parent_target_chars,
                child_target_chars=settings.retrieval.child_target_chars,
            )
            write_chunk_artifact(
                root=chunk_root,
                document_id=f"{document_id}__rag",
                parents=chunking_result.parents,
                children=chunking_result.children,
                chunk_report={
                    "document_id": f"{document_id}__rag",
                    "chunker_version": "chunker_v1",
                    "parent_count": len(chunking_result.parents),
                    "child_count": len(chunking_result.children),
                    "warnings": [],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            result["rag_elements"] = len(artifact.elements)
            result["rag_chunks"] = len(chunking_result.children)
            result["rag_tables"] = len(artifact.tables)
        except Exception as exc:
            result["status"] = "rag_failed"
            result["rag_error"] = f"{type(exc).__name__}: {exc}"

    # === Structured 路径：解析 → 反查校准 → 跨页修复 → 提取三表指标 → 入库 ===
    if structured_pages and not use_pdfplumber:
        try:
            structured_artifact = mineru_parser.parse(pdf_path, page_filter=structured_pages)
            structured_artifact.document["document_id"] = f"{document_id}__structured"
            structured_doc_dir = parsed_root / f"{document_id}__structured"
            write_parsed_artifact(parsed_root, structured_artifact)

            # 跨页表格修复：检测截断 → 合并页面 → 重解析 → 替换
            tables_jsonl = structured_doc_dir / "tables.jsonl"
            raw_tables = _read_tables_jsonl(tables_jsonl)
            truncated = find_truncated_tables(raw_tables)
            repaired_count = 0
            if truncated and mineru_parser is not None:
                print(f"\n    跨页修复: 检测到 {len(truncated)} 张截断表", flush=True)
                repair_results = []
                for tbl_idx, check in truncated:
                    print(f"    修复 p{check.page_start} {check.table_type} (缺: {check.missing_rows[:2]})", end=" ", flush=True)
                    repair = repair_truncated_table(
                        pdf_path=pdf_path,
                        table_check=check,
                        cache_dir=REPO_ROOT / "var" / "data" / "_merge_tmp",
                        mineru_parser=mineru_parser,
                    )
                    if repair.repaired:
                        repaired_count += 1
                        print(f"✓ ({repair.new_row_count}行)", flush=True)
                    else:
                        print(f"✗ ({repair.reason[:50]})", flush=True)
                    repair_results.append(repair)
                if repaired_count > 0:
                    _apply_repair_to_tables_jsonl(tables_jsonl, raw_tables, repair_results)

            # 修复8：反查校准——把 __rag 里的三表移到 __structured
            # 场景：page_filter LLM 把三表页错配到 rag（如格力 p111-120、平安 p122-139）
            # 此时 RAG 路径已解析完，__rag/tables.jsonl 含三表但 TableExtractor 读不到
            rag_tables_jsonl = parsed_root / f"{document_id}__rag" / "tables.jsonl"
            rag_elements_jsonl = parsed_root / f"{document_id}__rag" / "elements.jsonl"
            structured_elements_jsonl = structured_doc_dir / "elements.jsonl"
            moved_tables, moved_pages = recalibrate_financial_statements(
                rag_tables_jsonl, tables_jsonl,
                rag_elements_jsonl, structured_elements_jsonl,
            )
            if moved_tables:
                print(
                    f"    [反查校准] 从 __rag 移走 {len(moved_tables)} 张三表到 __structured，"
                    f"页码: {moved_pages[:5]}{'...' if len(moved_pages) > 5 else ''}",
                    flush=True,
                )
                result["recalibrated_pages"] = moved_pages
                result["recalibrated_tables"] = len(moved_tables)

            # 提取三表指标（SQLite 写入由 main 统一执行，避免并发写冲突）
            company_code = company_key.split("_")[0] if "_" in company_key else ""
            company_name = company_key.split("_", 1)[-1] if "_" in company_key else company_key
            # 注：llm_client 用于注释章节 keep/skip 决策；规则/pandas 失败时也用于回退提取
            try:
                from finsight_agent.infra.llm.client import LlmClient
                llm_client = LlmClient(timeout_seconds=90, max_tokens=8192)
            except Exception:
                llm_client = None
            extractor = TableExtractor(
                company_code=company_code,
                company_name=company_name,
                source_document_id=f"{document_id}__structured",
                normalizer=normalizer,
                llm_client=llm_client,
            )
            metric_records = extractor.extract_from_tables_file(tables_jsonl)

            result["structured_elements"] = len(structured_artifact.elements)
            result["structured_tables"] = len(structured_artifact.tables)
            result["structured_metrics"] = len(metric_records)
            result["structured_repaired"] = repaired_count
            result["metric_records"] = metric_records
            result["company_name"] = company_name
        except Exception as exc:
            result["status"] = "structured_failed"
            result["structured_error"] = f"{type(exc).__name__}: {exc}"

    return result


def process_company_with_retry(
    *,
    max_retries: int = 2,
    **kwargs,
) -> dict:
    """process_company 的重试包装，针对代理/SSL 间歇性失败。

    MinerU API 无限流，但本地代理到阿里云 OSS 的 SSL 握手偶发失败，
    重试 2 次（间隔 5s/10s）可覆盖大部分场景。

    注意：process_company 内部会吞掉异常转为 result["status"] = "rag_failed"/"structured_failed"，
    所以这里既要处理抛出的异常，也要检查返回 result 里的网络错误。
    """
    _RETRY_KEYWORDS = ("Proxy", "SSL", "Connection", "Timeout", "RemoteDisconnected")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = process_company(**kwargs)
        except Exception as exc:
            # process_company 外层抛出的异常（少见）
            last_exc = exc
            exc_name = type(exc).__name__
            retryable = any(kw in exc_name for kw in _RETRY_KEYWORDS) or "SSL" in str(exc)
            if not retryable or attempt >= max_retries:
                raise
            wait = 5 * (attempt + 1)
            company_key = kwargs.get("company_key", "?")
            print(f"    [{company_key}] 重试 {attempt + 1}/{max_retries} ({exc_name}, 等待 {wait}s) ...", flush=True)
            time.sleep(wait)
            continue

        # process_company 正常返回，检查是否因网络错误失败
        if result["status"] != "ok" and attempt < max_retries:
            err_msg = result.get("rag_error") or result.get("structured_error") or ""
            retryable = any(kw in err_msg for kw in _RETRY_KEYWORDS)
            if retryable:
                wait = 5 * (attempt + 1)
                company_key = kwargs.get("company_key", "?")
                print(f"    [{company_key}] 重试 {attempt + 1}/{max_retries} ({result['status']}, 等待 {wait}s) ...", flush=True)
                time.sleep(wait)
                continue
        return result
    raise last_exc  # type: ignore[misc]


def main() -> int:
    args = parse_args()
    settings = load_settings()

    if not PAGE_FILTER_JSON.exists():
        print(f"错误：找不到 page_filter JSON: {PAGE_FILTER_JSON}")
        return 1

    page_filter_data = json.loads(PAGE_FILTER_JSON.read_text(encoding="utf-8"))
    documents = page_filter_data.get("documents", {})

    raw_root = settings.retrieval.raw_filings_root
    parsed_root = settings.retrieval.parsed_filings_root
    chunk_root = settings.retrieval.chunked_filings_root

    # 过滤待处理文档
    # 展平 company_codes（支持逗号分隔）
    flat_codes: list[str] = []
    if args.company_codes:
        for c in args.company_codes:
            flat_codes.extend([s.strip() for s in c.split(",") if s.strip()])

    todo: list[tuple[str, dict]] = []
    for company_key, doc_info in documents.items():
        source = doc_info.get("source", "")
        kept_pages = doc_info.get("kept_pages", [])
        if source in ("failed", "skipped_too_short", "error"):
            continue
        if not kept_pages:
            continue
        if flat_codes:
            if not any(code in company_key for code in flat_codes):
                continue
        todo.append((company_key, doc_info))

    print(f"待解析文档: {len(todo)} 份")
    print(f"  总保留页数: {sum(len(d.get('kept_pages', [])) for _, d in todo)}")
    print(f"  解析器: {'pdfplumber' if args.use_pdfplumber else 'MinerU API'}")
    print("=" * 80, flush=True)

    # 断点续传
    if not args.force:
        existing_ids = load_parsed_doc_ids(parsed_root)
        print(f"已解析 {len(existing_ids)} 份，将跳过（用 --force 强制重解析）")
    else:
        existing_ids = set()
        print("强制重新解析所有文档")

    # 初始化解析器
    if args.use_pdfplumber:
        mineru_parser = None
        pdfplumber_parser = PdfplumberDocumentParser()
    else:
        mineru_parser = MineruDocumentParser(cache_dir=MINERU_CACHE_DIR)
        pdfplumber_parser = None

    # 初始化归一化器
    normalizer: MetricNormalizer | None = None
    if not args.use_pdfplumber:
        aliases_path = settings.structured_data.aliases_path
        if args.build_aliases:
            from finsight_agent.infra.llm.client import LlmClient

            normalizer = MetricNormalizer(
                aliases_path=aliases_path,
                llm_client=LlmClient(),
            )
            print(f"归一化模式：--build-aliases（aliases: {aliases_path}）")
        else:
            normalizer = MetricNormalizer(aliases_path=aliases_path)
            if aliases_path.exists():
                print(f"归一化模式：已加载 aliases JSON（{len(normalizer.aliases)} 条映射）")
            else:
                print(f"归一化模式：仅 _KNOWN_ALIASES（{len(normalizer.aliases)} 条），建议先跑 --build-aliases")

    success_count = 0
    skip_count = 0
    fail_count = 0
    total_rag_chunks = 0
    total_structured_tables = 0
    total_structured_metrics = 0
    all_metric_records: list = []

    # 预过滤：跳过文件不存在和断点续传
    runnable: list[tuple[int, str, dict]] = []
    for idx, (company_key, doc_info) in enumerate(todo, 1):
        pdf_path = REPO_ROOT / doc_info["pdf_path"]
        if not pdf_path.exists():
            print(f"[{idx:>3}/{len(todo)}] SKIP | 文件不存在 | {doc_info['pdf_path']}")
            skip_count += 1
            continue
        document_id = build_document_id(pdf_path, raw_root)
        if document_id in existing_ids and not args.force:
            skip_count += 1
            continue
        runnable.append((idx, company_key, doc_info))

    workers = max(1, min(args.workers, len(runnable))) if runnable else 1
    print(f"并行解析: {workers} workers，待处理 {len(runnable)} 份")
    print("=" * 80, flush=True)

    completed_results: list[dict] = []
    t0 = time.time()

    def _run_one(idx: int, company_key: str, doc_info: dict) -> dict:
        """单个公司解析任务（线程内执行）。"""
        doc_t0 = time.time()
        result = process_company_with_retry(
            company_key=company_key,
            doc_info=doc_info,
            raw_root=raw_root,
            parsed_root=parsed_root,
            chunk_root=chunk_root,
            settings=settings,
            mineru_parser=mineru_parser,
            pdfplumber_parser=pdfplumber_parser,
            use_pdfplumber=args.use_pdfplumber,
            normalizer=normalizer,
        )
        result["_elapsed"] = time.time() - doc_t0
        result["_company_key"] = company_key
        result["_idx"] = idx
        return result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_one, idx, company_key, doc_info): (idx, company_key)
            for idx, company_key, doc_info in runnable
        }
        for future in as_completed(futures):
            idx, company_key = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                fail_count += 1
                print(
                    f"[{idx:>3}/{len(todo)}] FAIL | {company_key} | "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                continue
            elapsed = result.get("_elapsed", 0)
            if result["status"] == "ok":
                success_count += 1
                total_rag_chunks += result["rag_chunks"]
                total_structured_tables += result["structured_tables"]
                total_structured_metrics += result.get("structured_metrics", 0)
                all_metric_records.extend(result.get("metric_records", []))
                completed_results.append(result)
                print(
                    f"[{idx:>3}/{len(todo)}] OK   | {company_key} | "
                    f"rag {result['rag_elements']}e/{result['rag_chunks']}c, "
                    f"struct {result['structured_elements']}e/{result['structured_tables']}t/{result.get('structured_metrics', 0)}m, "
                    f"{elapsed:.1f}s",
                    flush=True,
                )
            else:
                fail_count += 1
                err = result.get("rag_error") or result.get("structured_error") or result["status"]
                # 部分成功也收集 metric_records（structured 可能成功，rag 失败）
                if result.get("metric_records"):
                    all_metric_records.extend(result["metric_records"])
                    completed_results.append(result)
                print(f"[{idx:>3}/{len(todo)}] PART | {company_key} | {err} ({elapsed:.1f}s)", flush=True)

    # 统一串行写 SQLite（避免并发写冲突）
    if completed_results and not args.use_pdfplumber:
        write_t0 = time.time()
        repo = MetricRepository(sqlite_path=settings.structured_data.sqlite_path)
        for result in completed_results:
            records = result.get("metric_records", [])
            company_name = result.get("company_name", "")
            if records and company_name:
                repo.save_records_for_company(company_name, records)
        print(f"SQLite 写入: {len(completed_results)} 家公司，{time.time() - write_t0:.1f}s", flush=True)

    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print("解析完成")
    print("=" * 80)
    print(f"  成功: {success_count}")
    print(f"  跳过: {skip_count}")
    print(f"  失败: {fail_count}")
    print(f"  总 RAG chunks: {total_rag_chunks}")
    print(f"  总 Structured tables: {total_structured_tables}")
    print(f"  总 Structured metrics: {total_structured_metrics}")
    print(f"  耗时: {elapsed:.1f}s")

    # --build-aliases：构建映射表 + 重新归一化 + 重新写入 SQLite
    if args.build_aliases and all_metric_records and normalizer is not None:
        print("\n" + "=" * 80)
        print("构建 metric_name 映射表（LLM 批量调用）")
        print("=" * 80, flush=True)

        aliases_t0 = time.time()
        new_aliases = normalizer.build_aliases_from_records(all_metric_records)
        print(f"  新增映射: {len(new_aliases)} 条")
        print(f"  总映射: {len(normalizer.aliases)} 条")
        print(f"  耗时: {time.time() - aliases_t0:.1f}s")

        if new_aliases:
            print("\n重新归一化并写入 SQLite ...", flush=True)
            renorm_t0 = time.time()
            repo = MetricRepository(sqlite_path=settings.structured_data.sqlite_path)
            # 按公司分组，重新归一化 metric_name 后 upsert
            grouped: dict[str, list] = defaultdict(list)
            for record in all_metric_records:
                record.metric_name = normalizer.normalize(record.metric_label)
                grouped[record.company_name].append(record)
            for company_name, records in grouped.items():
                repo.save_records_for_company(company_name, records)
            print(f"  重新归一化 {len(all_metric_records)} 条记录，{len(grouped)} 家公司")
            print(f"  耗时: {time.time() - renorm_t0:.1f}s")

    # 重建索引（只对 RAG chunks）
    if not args.skip_index and success_count > 0:
        print("\n" + "=" * 80)
        print("重建检索索引（sparse + dense）")
        print("=" * 80, flush=True)

        index_t0 = time.time()
        facade = build_retrieval_facade()

        print("  sparse (BM25) ...", end=" ", flush=True)
        sparse_count = facade.sparse_facade.rebuild_index()
        print(f"OK ({sparse_count} chunks)")

        print("  dense (Qdrant) ...", end=" ", flush=True)
        dense_count = facade.dense_facade.rebuild_index()
        print(f"OK ({dense_count} chunks)")

        facade.close()
        print(f"  索引重建完成: sparse={sparse_count}, dense={dense_count}, "
              f"耗时 {time.time() - index_t0:.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
