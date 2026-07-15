"""跨页表格修复：检测截断的跨页表，合并页面后重解析。

流程：
  1. check_table_completeness: 检测 A 类表是否缺少关键汇总行
  2. merge_pages_to_single_pdf: 用 pypdf 把多页垂直拼接成单页 PDF
  3. MineruDocumentParser.parse(merged_pdf): 重解析合并后的单页
  4. replace_truncated_table: 用重解析结果替换原截断 table

适用场景：
  - 表头列名被 PDF 跨页切割，MinerU 在第二页识别失败
  - 跨页表只解析了第一页内容，缺少汇总行
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdf


# ============================================================
# 1. 完整性检查：检测截断的跨页表
# ============================================================

# 每类表的关键汇总行（必须出现在完整表里）
TABLE_SUMMARY_ROWS: dict[str, list[str]] = {
    "资产负债表": ["资产总计", "负债和所有者权益总计"],
    "利润表": ["净利润", "基本每股收益"],
    "现金流量表": ["期末现金及现金等价物余额"],
    "权益变动表": ["四、本期期末余额"],
}

# 推断表类型的关键字（按优先级排序，权益变动表要先于资产负债表匹配）
# 关键词必须真正专属，避免误判：
#   - "综合收益总额"不能用：利润表里也有"六、综合收益总额"行
#   - "所有者权益合计"不能用：资产负债表里也有这一行
# 权益变动表专属：本期期末余额/本年期初余额/所有者权益内部结转（这三个绝对不会出现在其他三表里）
TABLE_TYPE_KEYWORDS: dict[str, list[str]] = {
    "权益变动表": ["本期期末余额", "本年期初余额", "所有者权益内部结转"],
    "现金流量表": ["经营活动产生的现金流量", "投资活动产生的现金流量"],
    "利润表": ["营业收入", "营业成本", "净利润"],
    "资产负债表": ["资产总计", "负债合计", "流动资产合计"],
}


@dataclass(slots=True)
class CompletenessCheck:
    """单张表的完整性检查结果。"""
    table_index: int
    page_start: int
    row_count: int
    table_type: str | None
    is_complete: bool
    missing_rows: list[str]
    reason: str


def infer_table_type(table_markdown: str) -> str | None:
    """推断表的财务类型（按优先级顺序匹配，避免权益变动表被误判成资产负债表）。"""
    # 优先级：权益变动表 > 现金流量表 > 利润表 > 资产负债表
    # 因为权益变动表里有"所有者权益合计"，会被误判成资产负债表
    for table_type in ("权益变动表", "现金流量表", "利润表", "资产负债表"):
        keywords = TABLE_TYPE_KEYWORDS[table_type]
        if any(kw in table_markdown for kw in keywords):
            return table_type
    return None


def check_table_completeness(
    *,
    table_index: int,
    table_markdown: str,
    page_start: int,
) -> CompletenessCheck:
    """检查单张表是否完整（含关键汇总行）。

    Returns:
        CompletenessCheck: 检查结果，is_complete=False 表示可能被截断
    """
    rows = table_markdown.count("\n") + 1
    if rows < 5:
        return CompletenessCheck(
            table_index=table_index,
            page_start=page_start,
            row_count=rows,
            table_type=None,
            is_complete=True,  # 小表不检查
            missing_rows=[],
            reason="small table, skip check",
        )

    table_type = infer_table_type(table_markdown)
    if table_type is None:
        return CompletenessCheck(
            table_index=table_index,
            page_start=page_start,
            row_count=rows,
            table_type=None,
            is_complete=True,  # 非三表不检查
            missing_rows=[],
            reason="not a financial statement table",
        )

    summary_rows = TABLE_SUMMARY_ROWS.get(table_type, [])
    missing = [row for row in summary_rows if row not in table_markdown]

    return CompletenessCheck(
        table_index=table_index,
        page_start=page_start,
        row_count=rows,
        table_type=table_type,
        is_complete=len(missing) == 0,
        missing_rows=missing,
        reason=f"{table_type} missing: {missing}" if missing else f"{table_type} complete",
    )


def find_truncated_tables(tables: list[dict]) -> list[tuple[int, CompletenessCheck]]:
    """找出所有被截断的 A 类表。

    Returns:
        List of (table_index_in_list, check_result)
    """
    truncated: list[tuple[int, CompletenessCheck]] = []
    for idx, tbl in enumerate(tables):
        md = str(tbl.get("table_markdown") or tbl.get("table_text") or "")
        page = int(tbl.get("page_start", 0))
        check = check_table_completeness(
            table_index=idx,
            table_markdown=md,
            page_start=page,
        )
        if not check.is_complete:
            truncated.append((idx, check))
    return truncated


# ============================================================
# 2. 页面合并：用 pypdf 把多页垂直拼接成单页 PDF
# ============================================================

def merge_pages_to_single_pdf(
    pdf_path: Path,
    page_numbers: list[int],
    output_path: Path,
) -> Path:
    """把指定页码垂直拼接成单页 PDF。

    Args:
        pdf_path: 原始 PDF 路径
        page_numbers: 要合并的页码（1-based，如 [103, 104, 105]）
        output_path: 输出 PDF 路径

    Returns:
        输出 PDF 路径

    实现思路：
        用 pypdf 创建新 PDF，把多页内容垂直堆叠到一张大页上。
        新页面高度 = 各页高度之和，宽度 = 最大宽度。
    """
    reader = pypdf.PdfReader(str(pdf_path))
    writer = pypdf.PdfWriter()

    # 收集所有要合并的页
    pages_to_merge: list[pypdf.PageObject] = []
    for page_num in page_numbers:
        if 1 <= page_num <= len(reader.pages):
            pages_to_merge.append(reader.pages[page_num - 1])

    if not pages_to_merge:
        raise ValueError(f"no valid pages to merge: {page_numbers}")

    # 计算合并后的页面尺寸
    max_width = max(float(p.mediabox.width) for p in pages_to_merge)
    total_height = sum(float(p.mediabox.height) for p in pages_to_merge)

    # 创建空白大页
    merged_page = pypdf.PageObject.create_blank_page(width=max_width, height=total_height)

    # 从下往上依次合并每页（pypdf 的 y 轴向上）
    current_y = 0.0
    for src_page in pages_to_merge:
        src_width = float(src_page.mediabox.width)
        src_height = float(src_page.mediabox.height)
        # 水平居中
        x_offset = (max_width - src_width) / 2
        # pypdf merge_transformed_page: 把 src_page 放到 (x_offset, current_y)
        merged_page.merge_translated_page(
            src_page,
            tx=x_offset,
            ty=current_y,
            expand=False,
        )
        current_y += src_height

    writer.add_page(merged_page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)
    return output_path


# ============================================================
# 3. 跨页表修复：合并→重解析→替换
# ============================================================

@dataclass(slots=True)
class RepairResult:
    """跨页表修复结果。"""
    original_table_index: int
    original_page: int
    table_type: str
    missing_rows: list[str]
    repaired: bool
    new_markdown: str
    new_row_count: int
    merged_pages: list[int]
    reason: str


def repair_truncated_table(
    *,
    pdf_path: Path,
    table_check: CompletenessCheck,
    max_merge_pages: int = 3,
    cache_dir: Path | None = None,
    mineru_parser: Any = None,
) -> RepairResult:
    """修复单个截断的跨页表。

    Args:
        pdf_path: 原始 PDF 路径
        table_check: 完整性检查结果
        max_merge_pages: 最多合并几页（默认 3）
        cache_dir: 临时文件目录
        mineru_parser: MineruDocumentParser 实例

    Returns:
        RepairResult: 修复结果
    """
    if mineru_parser is None:
        return RepairResult(
            original_table_index=table_check.table_index,
            original_page=table_check.page_start,
            table_type=table_check.table_type or "unknown",
            missing_rows=table_check.missing_rows,
            repaired=False,
            new_markdown="",
            new_row_count=0,
            merged_pages=[],
            reason="no mineru_parser provided",
        )

    # 合并截断表的起始页 + 后续 max_merge_pages-1 页
    start_page = table_check.page_start
    pages_to_merge = list(range(start_page, start_page + max_merge_pages))

    # 准备临时 PDF 路径
    if cache_dir is None:
        cache_dir = Path("var/data/_merge_tmp")
    temp_pdf = cache_dir / f"merged_p{start_page}_{start_page + max_merge_pages - 1}.pdf"

    try:
        # 1. 合并页面
        merge_pages_to_single_pdf(pdf_path, pages_to_merge, temp_pdf)
    except Exception as exc:
        return RepairResult(
            original_table_index=table_check.table_index,
            original_page=start_page,
            table_type=table_check.table_type or "unknown",
            missing_rows=table_check.missing_rows,
            repaired=False,
            new_markdown="",
            new_row_count=0,
            merged_pages=[],
            reason=f"merge failed: {exc}",
        )

    try:
        # 2. 用 MinerU 重解析合并后的单页 PDF
        artifact = mineru_parser.parse(temp_pdf)
    except Exception as exc:
        return RepairResult(
            original_table_index=table_check.table_index,
            original_page=start_page,
            table_type=table_check.table_type or "unknown",
            missing_rows=table_check.missing_rows,
            repaired=False,
            new_markdown="",
            new_row_count=0,
            merged_pages=pages_to_merge,
            reason=f"reparse failed: {exc}",
        )

    # 3. 从重解析结果里找最大的 table（应该就是完整的跨页表）
    if not artifact.tables:
        return RepairResult(
            original_table_index=table_check.table_index,
            original_page=start_page,
            table_type=table_check.table_type or "unknown",
            missing_rows=table_check.missing_rows,
            repaired=False,
            new_markdown="",
            new_row_count=0,
            merged_pages=pages_to_merge,
            reason="reparse produced no tables",
        )

    # MinerU 可能把合并后的单页解析成多个 table 片段，需要拼接
    # 按 page_start 排序，把所有 table 的 markdown 拼起来
    sorted_tables = sorted(artifact.tables, key=lambda t: int(t.page_start or 0))
    merged_md = "\n".join(str(t.table_markdown or "") for t in sorted_tables if str(t.table_markdown or "").strip())
    new_md = merged_md
    new_rows = new_md.count("\n") + 1

    # 4. 验证修复结果是否真的包含之前缺失的汇总行
    still_missing = [r for r in table_check.missing_rows if r not in new_md]
    if still_missing:
        return RepairResult(
            original_table_index=table_check.table_index,
            original_page=start_page,
            table_type=table_check.table_type or "unknown",
            missing_rows=table_check.missing_rows,
            repaired=False,
            new_markdown=new_md,
            new_row_count=new_rows,
            merged_pages=pages_to_merge,
            reason=f"still missing after repair: {still_missing}",
        )

    return RepairResult(
        original_table_index=table_check.table_index,
        original_page=start_page,
        table_type=table_check.table_type or "unknown",
        missing_rows=table_check.missing_rows,
        repaired=True,
        new_markdown=new_md,
        new_row_count=new_rows,
        merged_pages=pages_to_merge,
        reason=f"repaired: merged {pages_to_merge}, {new_rows} rows",
    )


def apply_repair_to_tables(
    tables: list[dict],
    repair_results: list[RepairResult],
) -> list[dict]:
    """把修复后的 table_markdown 写回 tables 列表。"""
    repaired_map = {r.original_table_index: r for r in repair_results if r.repaired}
    if not repaired_map:
        return tables

    new_tables = []
    for idx, tbl in enumerate(tables):
        if idx in repaired_map:
            repair = repaired_map[idx]
            new_tbl = dict(tbl)
            new_tbl["table_markdown"] = repair.new_markdown
            new_tbl["table_text"] = repair.new_markdown.replace("|", " ").replace("\n", " ")
            new_tbl["_repaired"] = True
            new_tbl["_repaired_pages"] = repair.merged_pages
            new_tables.append(new_tbl)
        else:
            new_tables.append(tbl)
    return new_tables
