"""表格提取器：从 MinerU 解析的 tables.jsonl 提取三表指标成 MetricRecord。

策略（精简版）：
  - 只对三表+权益变动表（A类）做规则提取，生成 MetricRecord
  - 其他表（B类明细表/空表）直接跳过，原始 markdown 已在 tables.jsonl 里
  - 规则失败的 A类表回退 LLM 提取

不做的事：
  - 不生成 table_records.jsonl（B类表需要时直接读 tables.jsonl）
  - 不对 B类表做 LLM 提取（查询频率低，不值得）

判断 A 类的条件：
  1. 表头含期间关键词（期末余额/期初余额/2024年度 等）
  2. 表头第一列是通用项目词（"项目"等），不是维度词（"账龄""单位名称"等）
"""
from __future__ import annotations

import io
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .models import MetricRecord

if TYPE_CHECKING:
    from .metric_normalizer import MetricNormalizer


# ============================================================
# 数据模型
# ============================================================

@dataclass(slots=True)
class ExtractionResult:
    """单张表的提取结果。"""

    table_id: str
    table_type: str  # metric_series / skip
    metric_records: list[MetricRecord]
    reason: str


# ============================================================
# 规则提取：识别 A 类表头和指标行
# ============================================================

# A类表的列名特征：含期间关键词
PERIOD_HEADER_PATTERNS = [
    re.compile(r"期末余额"),
    re.compile(r"期初余额"),
    re.compile(r"本期金额"),
    re.compile(r"上期金额"),
    re.compile(r"本期发生额"),
    re.compile(r"上期发生额"),
    # "本年年末余额"/"上年年末余额"（海康威视等）
    re.compile(r"[本上]年年末余额"),
    # "2024年度"/"2024 年度"（带空格）
    re.compile(r"\d{4}\s*年度"),
    # "2024年12月31日"/"2024 年 12 月 31 日"（带空格）
    re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"),
    # 繁体："二零二四年"/"二零二四年十二月三十一日"（中国国航、广汽集团等港交所双语年报）
    re.compile(r"二[零〇一二三四五六七八九]{3}\s*年"),
    # 繁体："截至二零二四年十二月三十一日止年度"
    re.compile(r"截至二[零〇一二三四五六七八九]{3}\s*年"),
    # "2024年"/"2023年"（银行股双行表头：本集团/本行 + 年份，如交通银行）
    # 安全性：B 类表第一列是维度词（账龄等），已被 B_CLASS_FIRST_COL_PATTERNS 排除
    re.compile(r"\b\d{4}\s*年(?![度月])"),
]

# 明确是 B类表的第一列词（维度词，说明是明细表）
B_CLASS_FIRST_COL_PATTERNS = [
    re.compile(r"^账龄"),
    re.compile(r"^单位名称"),
    re.compile(r"^类别"),
    re.compile(r"^客户[一二三四五六七八九十]"),
    re.compile(r"^供应商[一二三四五六七八九十]"),
    re.compile(r"^项目名称"),
    re.compile(r"^序号"),
]

# 跳过的纯分类行（没有数值）
CATEGORY_ROW_PATTERNS = [
    re.compile(r"^流动资产[:：]?\s*$"),
    re.compile(r"^非流动资产[:：]?\s*$"),
    re.compile(r"^流动负债[:：]?\s*$"),
    re.compile(r"^非流动负债[:：]?\s*$"),
    re.compile(r"^所有者权益[:：]?\s*$"),
    # 现金流量表的分类行（下面有子项，本身无数值）
    re.compile(r"^一、经营活动"),
    re.compile(r"^一、筹资活动"),
    re.compile(r"^一、投资活动"),
    # 注意：利润表的"一、营业总收入"/"一、营业总成本"是真实指标行（有数值），不应跳过
]

# 非指标名：明细表里的实体名/分桶维度，不应作为 metric_name
NON_METRIC_NAME_PATTERNS = [
    re.compile(r"^客户[一二三四五六七八九十]$"),
    re.compile(r"^供应商[一二三四五六七八九十]$"),
    re.compile(r"^\d+年以内"),
    re.compile(r"^\d+至\d+年"),
    re.compile(r"^\d+年以上"),
    re.compile(r"^其中[:：]?\s*$"),
    re.compile(r"^合计$"),
    re.compile(r"^小计$"),
    re.compile(r"^按单项计提"),
    re.compile(r"^按组合计提"),
    re.compile(r"^银行承兑票据"),
    re.compile(r"^商业承兑票据"),
    re.compile(r"^原材料$"),
    re.compile(r"^在产品$"),
    re.compile(r"^库存商品$"),
    re.compile(r"^发出商品$"),
    re.compile(r"^委托加工物资"),
    re.compile(r"^自制半成品"),
]

# 数值行：第一列是指标名，后续列含数字
NUMERIC_VALUE_PATTERN = re.compile(r"[\d,]+\.\d+|[\d,]{3,}|\d+\.\d+%?")


def is_metric_series_table(table_markdown: str) -> bool:
    """判断是否是 A 类表（指标时间序列）。

    条件：
    1. 表头含期间关键词（期末余额/期初余额/2024年度 等）
    2. 表头第一列不是维度词（"账龄"/"单位名称"等）
    """
    lines = table_markdown.strip().split("\n")
    if not lines:
        return False

    for line in lines[:3]:
        if not any(p.search(line) for p in PERIOD_HEADER_PATTERNS):
            continue
        cells = _split_markdown_row(line)
        if not cells:
            continue
        first_col = cells[0].strip()
        if any(p.match(first_col) for p in B_CLASS_FIRST_COL_PATTERNS):
            return False
        return True

    return False


def extract_metrics_by_rule(
    table_markdown: str,
    *,
    company_code: str,
    company_name: str,
    source_document_id: str,
    table_id: str,
    caption: str,
    period_end: str,
    normalizer: "MetricNormalizer | None" = None,
    statement_type: str = "unknown",
    source_section: str = "unknown",
    resolved_unit: str = "元",
) -> list[MetricRecord]:
    """规则提取：解析 A 类表的 markdown，返回 MetricRecord 列表。

    列对齐策略（治本版）：
    1. 识别表头每一列的类型：项目列 / 附注列 / 期间列
    2. 数据行按相同的列下标对齐：跳过附注列，项目列取 metric_name，期间列取 value
    3. 强制约束 value_cells 与 period_headers 数量一致，不一致则该行降置信度
    """
    lines = table_markdown.strip().split("\n")
    if len(lines) < 2:
        return []

    # 找表头行（含期间关键词的行）
    header_idx = -1
    for i, line in enumerate(lines[:3]):
        if any(p.search(line) for p in PERIOD_HEADER_PATTERNS):
            header_idx = i
            break
    if header_idx < 0:
        return []

    header_cells = _split_markdown_row(lines[header_idx])
    if len(header_cells) < 2:
        return []

    # 识别每一列的类型
    col_types = _classify_header_columns(header_cells)
    # 期间列的下标（用于取 period_headers）
    period_col_indices = [i for i, t in enumerate(col_types) if t == "period"]
    if not period_col_indices:
        return []

    # 项目列的下标（用于取 metric_name）
    has_metric_col = any(t == "metric" for t in col_types)
    if has_metric_col:
        metric_col_idx = next(i for i, t in enumerate(col_types) if t == "metric")
        # 数据行的期间列下标 = 表头期间列下标（对齐）
        data_period_indices = period_col_indices
    else:
        # 无项目列：表头全是期间列，数据行第一列是指标名，期间列下标 +1
        metric_col_idx = 0
        data_period_indices = [i + 1 for i in period_col_indices]

    # period_headers：只保留期间列的表头文本
    period_headers = [header_cells[i].strip() for i in period_col_indices]

    records: list[MetricRecord] = []
    for line in lines[header_idx + 1:]:
        cells = _split_markdown_row(line)
        if len(cells) < 2:
            continue

        # 取 metric_name：从项目列取
        if metric_col_idx >= len(cells):
            continue
        metric_name = cells[metric_col_idx].strip()
        if not metric_name or _is_category_row(metric_name) or _is_non_metric_name(metric_name):
            continue

        # 归一化：中文原文 → 标准英文 key
        metric_label = metric_name
        if normalizer is not None:
            metric_name = normalizer.normalize(metric_name)

        # 取 value_cells：按数据行期间列下标取值
        value_cells: list[str] = []
        for col_idx in data_period_indices:
            if col_idx >= len(cells):
                value_cells.append("")
                continue
            v = cells[col_idx].strip()
            value_cells.append(v)

        # 列对齐校验：value_cells 数量必须 == period_headers 数量
        if len(value_cells) != len(period_headers):
            # 不一致说明列对齐失败，跳过该行
            continue

        for col_idx, value in enumerate(value_cells):
            if not value:
                continue
            if not NUMERIC_VALUE_PATTERN.search(value):
                continue

            period_header = period_headers[col_idx]
            time_scope = _normalize_time_scope(period_header)
            # 按列解析 period_end：2023年列 → 2023-12-31
            col_period_end = _infer_period_end_from_header(period_header) or period_end
            # 比率列标 "%"，货币列用解析出的真实单位；绝不改写数值。
            col_unit = "%" if _is_ratio_header(period_header) else resolved_unit

            records.append(MetricRecord(
                company_name=company_name,
                company_code=company_code,
                metric_name=metric_name,
                metric_label=metric_label,
                time_scope=time_scope,
                period_end=col_period_end,
                value=value,
                unit=col_unit,
                currency="CNY",
                source_type="annual_report",
                source_document_id=source_document_id,
                source_table_id=table_id,
                source_caption=caption,
                confidence="high" if NUMERIC_VALUE_PATTERN.fullmatch(value) else "medium",
                statement_type=statement_type,
                source_section=source_section,
            ))

    return records


def _split_markdown_row(line: str) -> list[str]:
    """分割 markdown 表格行，去掉管道符和前后空格。"""
    cleaned = line.strip().strip("|").strip()
    if not cleaned:
        return []
    return [cell.strip() for cell in cleaned.split("|")]


def _is_category_row(name: str) -> bool:
    """判断是否是纯分类行（如"流动资产:"），应跳过。"""
    return any(p.match(name) for p in CATEGORY_ROW_PATTERNS)


def _is_non_metric_name(name: str) -> bool:
    """判断是否是非指标名（明细表的实体名/分桶维度），应跳过。"""
    return any(p.match(name) for p in NON_METRIC_NAME_PATTERNS)


def _normalize_time_scope(header: str) -> str:
    """把表头期间描述标准化成 time_scope 字符串。

    归一化规则（解决格式不统一问题）：
    - "期末余额"/"期初余额" → 原样
    - "本期金额"/"本期发生额" → "本期"
    - "上期金额"/"上期发生额" → "上期"
    - "2024年度"/"2024 年度"/"2024年" → "2024年"（去掉空格和"度"）
    - "2024年12月31日"/"2024 年 12 月 31 日" → "2024年"（提取年份）
    - "2023年(经重述)"/"2023年12月31日(经重述)" → "2023年"（去掉经重述标记）

    注意："(经重述)"是会计标记，不是期间标识。保留它会导致同一期间
    出现"2023年"和"2023年(经重述)"两个 time_scope，破坏精确匹配。
    同一期间的多条记录靠 statement_type 区分（合并/母公司）。
    """
    header = header.strip()
    if "期末余额" in header:
        return "期末余额"
    if "期初余额" in header:
        return "期初余额"
    if "本期金额" in header or "本期发生额" in header:
        return "本期"
    if "上期金额" in header or "上期发生额" in header:
        return "上期"
    # 年份归一化：提取 4 位年份 + "年"，忽略"(经重述)"标记
    year_match = re.search(r"(\d{4})\s*年", header)
    if year_match:
        year = year_match.group(1)
        return f"{year}年"
    # 繁体年份归一化
    tc_year_match = re.search(r"(二[零〇一二三四五六七八九]{3})\s*年", header)
    if tc_year_match:
        return header  # 繁体保持原样，查询时单独处理
    return header


def _classify_header_columns(header_cells: list[str]) -> list[str]:
    """识别表头每一列的类型：metric / note / period。

    类型判定：
    - period：匹配期间关键词（期末余额/期初余额/2024年 等）
    - note：匹配附注关键词（附注七/附注/注/Note 等以"附注"开头或纯"注"）
    - metric：其他（项目/指标名等）

    这样数据行可以按相同的列下标对齐，不再依赖"丢第一列"和"跳1-3位数字"启发式。
    """
    col_types: list[str] = []
    for cell in header_cells:
        cell = cell.strip()
        if any(p.search(cell) for p in PERIOD_HEADER_PATTERNS):
            col_types.append("period")
        elif re.search(r"^附注|^注$|^Note$|^项目$", cell, re.IGNORECASE):
            # "附注七"/"附注"/"注"/"Note"/"项目" 都是表头标识列，不是期间列
            col_types.append("note" if "项目" not in cell else "metric")
        else:
            col_types.append("metric")
    return col_types


def _infer_period_end_from_header(header: str) -> str | None:
    """从期间列表头解析 period_end 日期。

    - "2024年12月31日" → "2024-12-31"
    - "2024年度"/"2024年" → "2024-12-31"（默认年末）
    - "2023年(经重述)" → "2023-12-31"
    - "期末余额"/"期初余额" → None（无法判断具体年份，用全表 period_end）
    """
    header = header.strip()
    # 完整日期：2024年12月31日 / 2024 年 12 月 31 日
    date_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", header)
    if date_match:
        y, m, d = date_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    # 纯年份：2024年度 / 2024年 / 2024 年度
    year_match = re.search(r"(\d{4})\s*年", header)
    if year_match:
        year = year_match.group(1)
        return f"{year}-12-31"
    return None


# ============================================================
# pandas HTML 解析（治本版：自动展开合并单元格、识别表头、转 float）
# ============================================================

def _is_ratio_header(header: str) -> bool:
    """判断期间列表头是否为比率列（如"占比(%)""增长率"），这类不应带货币单位。"""
    return bool(re.search(r"%|\b比率\b|比例|占比|百分比|百分点", header or ""))


def _parse_html_with_pandas(
    table_html: str,
    *,
    company_code: str,
    company_name: str,
    source_document_id: str,
    table_id: str,
    caption: str,
    period_end: str,
    normalizer: "MetricNormalizer | None" = None,
    statement_type: str = "unknown",
    source_section: str = "unknown",
    resolved_unit: str = "元",
) -> list[MetricRecord]:
    """用 pandas.read_html 解析 HTML 表格，返回 MetricRecord 列表。

    优势（vs 正则解析 markdown）：
    1. 自动展开 colspan/rowspan 合并单元格（治本列错位）
    2. 自动识别表头行 vs 数据行
    3. 自动处理负值括号表示法 (123) → -123
    4. 自动去千分位逗号转 float

    流程：
    1. pandas.read_html → DataFrame（header 自动识别）
    2. 识别项目列（第一列含中文指标名）和期间列（表头匹配 PERIOD_HEADER_PATTERNS）
    3. 遍历数据行：项目列取 metric_name，期间列取 value，生成 MetricRecord
    """
    if not table_html.strip():
        return []

    try:
        import pandas as pd
    except ImportError:
        return []

    # pandas.read_html 需要完整的 <table>...</table>
    if "<table" not in table_html.lower():
        return []

    try:
        dfs = pd.read_html(io.StringIO(table_html), header=None, flavor="bs4")
    except Exception:
        try:
            dfs = pd.read_html(io.StringIO(table_html), header=None)
        except Exception:
            return []

    if not dfs:
        return []

    df = dfs[0]
    if df.empty or df.shape[0] < 2 or df.shape[1] < 2:
        return []

    # 把所有单元格转成字符串，去除 NaN
    df = df.fillna("").astype(str).apply(lambda col: col.str.strip())

    # 找表头行：含期间关键词的行（前 3 行内）
    header_idx = -1
    for i in range(min(3, df.shape[0])):
        row_vals = [str(v) for v in df.iloc[i].tolist()]
        if any(any(p.search(v) for p in PERIOD_HEADER_PATTERNS) for v in row_vals):
            header_idx = i
            break
    if header_idx < 0:
        return []

    header_cells = [str(v) for v in df.iloc[header_idx].tolist()]
    col_types = _classify_header_columns(header_cells)
    period_col_indices = [i for i, t in enumerate(col_types) if t == "period"]
    if not period_col_indices:
        return []

    # 项目列下标
    has_metric_col = any(t == "metric" for t in col_types)
    if has_metric_col:
        metric_col_idx = next(i for i, t in enumerate(col_types) if t == "metric")
    else:
        metric_col_idx = 0

    period_headers = [header_cells[i].strip() for i in period_col_indices]

    records: list[MetricRecord] = []
    # 数据行从 header_idx + 1 开始
    for row_idx in range(header_idx + 1, df.shape[0]):
        row_cells = [str(v) for v in df.iloc[row_idx].tolist()]
        if len(row_cells) < 2:
            continue

        if metric_col_idx >= len(row_cells):
            continue
        metric_name = row_cells[metric_col_idx].strip()
        if not metric_name or _is_category_row(metric_name) or _is_non_metric_name(metric_name):
            continue
        # 跳过纯数字行（无指标名）
        if re.match(r"^[\d,.\s]+$", metric_name):
            continue

        metric_label = metric_name
        if normalizer is not None:
            metric_name = normalizer.normalize(metric_name)

        # 取期间列的值
        value_cells: list[str] = []
        for col_idx in period_col_indices:
            if col_idx >= len(row_cells):
                value_cells.append("")
                continue
            v = row_cells[col_idx].strip()
            value_cells.append(v)

        if len(value_cells) != len(period_headers):
            continue

        for col_idx, value in enumerate(value_cells):
            if not value:
                continue
            # pandas 可能已把数值转成 float，统一转回字符串
            if value.endswith(".0"):
                value = value[:-2]
            if not NUMERIC_VALUE_PATTERN.search(value):
                continue

            period_header = period_headers[col_idx]
            time_scope = _normalize_time_scope(period_header)
            col_period_end = _infer_period_end_from_header(period_header) or period_end
            # 比率列（占比/增长率等）标 "%"，货币列用解析出的真实单位；绝不改写数值。
            col_unit = "%" if _is_ratio_header(period_header) else resolved_unit

            records.append(MetricRecord(
                company_name=company_name,
                company_code=company_code,
                metric_name=metric_name,
                metric_label=metric_label,
                time_scope=time_scope,
                period_end=col_period_end,
                value=value,
                unit=col_unit,
                currency="CNY",
                source_type="annual_report",
                source_document_id=source_document_id,
                source_table_id=table_id,
                source_caption=caption,
                confidence="high" if NUMERIC_VALUE_PATTERN.fullmatch(value) else "medium",
                statement_type=statement_type,
                source_section=source_section,
            ))

    return records


# ============================================================
# TableExtractor
# ============================================================

class TableExtractor:
    """表格提取器：只对三表做规则提取，其他表跳过。

    B类明细表不处理，原始 markdown 已在 tables.jsonl 里，
    需要时直接读那个文件按 caption/section_path 过滤即可。
    """

    def __init__(
        self,
        *,
        llm_client=None,
        company_code: str = "",
        company_name: str = "",
        source_document_id: str = "",
        normalizer: "MetricNormalizer | None" = None,
    ) -> None:
        self._company_code = company_code
        self._company_name = company_name
        self._source_document_id = source_document_id
        self._llm_client = llm_client  # 延迟构造，只在规则失败时用
        self._normalizer = normalizer

    def extract_from_tables_file(
        self,
        tables_jsonl_path: Path,
    ) -> list[MetricRecord]:
        """从 tables.jsonl 读取所有表格，只对 A类表提取 MetricRecord。

        返回 MetricRecord 列表（B类表跳过，原始数据已在 tables.jsonl）。
        """
        if not tables_jsonl_path.exists():
            return []

        # 从同目录 elements.jsonl 构建页码→报表口径映射 + 注释区页码集合 + 注释章节标题
        elements_path = tables_jsonl_path.parent / "elements.jsonl"
        stmt_type_map, notes_pages, notes_section_titles = _build_statement_type_map(elements_path)
        if stmt_type_map:
            consolidated_cnt = sum(1 for v in stmt_type_map.values() if v == "consolidated")
            parent_cnt = sum(1 for v in stmt_type_map.values() if v == "parent_only")
            print(f"  报表口径映射: consolidated={consolidated_cnt}页, parent_only={parent_cnt}页, 注释区={len(notes_pages)}页, 注释章节={len(notes_section_titles)}个", flush=True)

        # LLM 判断注释章节 keep/skip（含缓存）
        notes_decision_map: dict[str, int] = {}
        if notes_section_titles:
            unique_titles = list(dict.fromkeys(notes_section_titles.values()))  # 保序去重
            notes_decision_map = _decide_notes_sections_via_llm(
                llm_client=self._llm_client,
                section_titles=unique_titles,
                company_code=self._company_code,
                cache_dir=tables_jsonl_path.parent.parent.parent / "notes_section_decisions",
            )
            keep_cnt = sum(1 for v in notes_decision_map.values() if v == 1)
            print(f"  LLM 注释章节决策: keep={keep_cnt}/{len(notes_decision_map)}", flush=True)

        metric_records: list[MetricRecord] = []
        table_index = 0
        total_tables = 0

        with tables_jsonl_path.open(encoding="utf-8") as f:
            total_tables = sum(1 for line in f if line.strip())

        print(f"  共 {total_tables} 张表，提取A类指标表", flush=True)

        with tables_jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                table_index += 1
                raw_table = json.loads(stripped)
                table_id = raw_table.get("table_id") or f"{self._source_document_id}_table_{table_index:06d}"

                md_lines = (raw_table.get("table_markdown") or "").count("\n") + 1
                print(f"  [{table_index}/{total_tables}] p{raw_table.get('page_start', '?')} ({md_lines}行) ...", end=" ", flush=True)

                t0 = time.time()
                result = self._extract_single_table(
                    table_id=table_id, raw_table=raw_table,
                    stmt_type_map=stmt_type_map, notes_pages=notes_pages,
                    notes_section_titles=notes_section_titles,
                    notes_decision_map=notes_decision_map,
                )
                elapsed = time.time() - t0

                status_icon = {
                    "metric_series": f"✓A({len(result.metric_records)}指标)",
                    "skip": "·skip",
                }.get(result.table_type, "?")
                print(f"{status_icon} ({elapsed:.1f}s) | {result.reason[:50]}", flush=True)

                if result.metric_records:
                    metric_records.extend(result.metric_records)

        return metric_records

    def _extract_single_table(
        self,
        *,
        table_id: str,
        raw_table: dict,
        stmt_type_map: dict[int, str] | None = None,
        notes_pages: set[int] | None = None,
        notes_section_titles: dict[int, str] | None = None,
        notes_decision_map: dict[str, int] | None = None,
    ) -> ExtractionResult:
        """处理单张表：pandas 优先解析 HTML，fallback 正则；注释区查 LLM 决策。"""
        table_html = str(raw_table.get("table_html") or "")
        table_markdown = str(raw_table.get("table_markdown") or raw_table.get("table_text") or "")
        if not table_html.strip() and not table_markdown.strip():
            return ExtractionResult(table_id=table_id, table_type="skip", metric_records=[], reason="empty")

        # 注释区：查 LLM 决策（keep=1 继续提取并标 source_section='notes'，keep=0 跳过）
        page_start = int(raw_table.get("page_start") or 0)
        in_notes = False
        if notes_pages and page_start in notes_pages:
            nearest_title = _find_nearest_notes_title(page_start, notes_section_titles or {})
            if nearest_title and (notes_decision_map or {}).get(nearest_title, 0) == 1:
                in_notes = True
            else:
                skip_reason = f"notes skip (title={nearest_title or '未知'})"
                return ExtractionResult(table_id=table_id, table_type="skip", metric_records=[], reason=skip_reason)

        section_path = list(raw_table.get("section_path") or [])
        caption = str(raw_table.get("caption_text") or "").strip() or " > ".join(section_path)
        period_end = _infer_period_end(section_path, table_markdown or table_html)
        # 报表口径：优先用 elements.jsonl 页码映射，fallback 到 caption
        statement_type = "unknown"
        if stmt_type_map and page_start in stmt_type_map:
            statement_type = stmt_type_map[page_start]
        elif in_notes:
            statement_type = "consolidated"  # 注释区默认合并口径
        else:
            statement_type = _infer_statement_type(caption, section_path)

        # source_section 推断：注释区 → notes；三表区按 caption 推断
        source_section = _infer_source_section(statement_type, caption, in_notes)
        # 兜底：MinerU 可能漏掉报表标题导致 section_path 污染，
        # 用表格内容特征关键词校验/修正 source_section 和 statement_type。
        # 污染模式：合并利润表被标成"母公司资产负债表"（继承前一个 title），
        # 导致 source_section 和 statement_type 都错。内容兜底修正两者。
        if not in_notes:
            refined_section, refined_stype = _refine_section_by_content(
                source_section, statement_type, table_markdown, table_html
            )
            source_section = refined_section
            if refined_stype:
                statement_type = refined_stype
        # 该表真实单位（来自 MinerU 缓存文本块的单位声明，已透传至 raw_table）。
        # 仅用于正确标注 unit，绝不改写 value 数值。
        resolved_unit = str(raw_table.get("resolved_unit") or "元").strip() or "元"

        # pandas 优先解析 HTML（治本：自动展开合并单元格、识别表头、转 float）
        records: list[MetricRecord] = []
        if table_html.strip():
            records = _parse_html_with_pandas(
                table_html,
                company_code=self._company_code,
                company_name=self._company_name,
                source_document_id=self._source_document_id,
                table_id=table_id,
                caption=caption,
                period_end=period_end,
                normalizer=self._normalizer,
                statement_type=statement_type,
                source_section=source_section,
                resolved_unit=resolved_unit,
            )

        # pandas 失败或无 HTML：fallback 正则解析 markdown
        if not records and table_markdown.strip():
            lines = table_markdown.strip().split("\n")
            if len(lines) < 3:
                return ExtractionResult(table_id=table_id, table_type="skip", metric_records=[], reason=f"too few rows ({len(lines)})")
            if is_metric_series_table(table_markdown):
                records = extract_metrics_by_rule(
                    table_markdown,
                    company_code=self._company_code,
                    company_name=self._company_name,
                    source_document_id=self._source_document_id,
                    table_id=table_id,
                    caption=caption,
                    period_end=period_end,
                    normalizer=self._normalizer,
                    statement_type=statement_type,
                    source_section=source_section,
                    resolved_unit=resolved_unit,
                )

        if records:
            return ExtractionResult(
                table_id=table_id,
                table_type="metric_series",
                metric_records=records,
                reason=f"extracted {len(records)} metrics ({'html' if table_html.strip() else 'rule'}, notes={in_notes})",
            )

        # 规则/pandas 均失败，回退 LLM
        if self._llm_client is not None:
            llm_records = self._llm_fallback_extract(
                table_markdown=table_markdown or table_html,
                table_id=table_id,
                caption=caption,
                period_end=period_end,
                statement_type=statement_type,
                source_section=source_section,
                resolved_unit=resolved_unit,
            )
            if llm_records:
                return ExtractionResult(
                    table_id=table_id,
                    table_type="metric_series",
                    metric_records=llm_records,
                    reason=f"llm fallback extracted {len(llm_records)} metrics",
                )

        return ExtractionResult(
            table_id=table_id,
            table_type="skip",
            metric_records=[],
            reason="extraction failed (html+rule+llm)",
        )

    def _llm_fallback_extract(
        self,
        *,
        table_markdown: str,
        table_id: str,
        caption: str,
        period_end: str,
        statement_type: str = "unknown",
        source_section: str = "unknown",
        resolved_unit: str = "元",
    ) -> list[MetricRecord]:
        """LLM 回退提取（只在规则失败时调用）。resolved_unit 用于提示模型正确单位。"""
        try:
            client = self._llm_client or self._build_default_client()
            payload = client.complete_json(
                prompt_name="table_extractor",
                variables={
                    "system_prompt": TABLE_EXTRACTOR_LLM_PROMPT,
                    "company_code": self._company_code,
                    "company_name": self._company_name,
                    "section_path": caption,
                    "page_start": 0,
                    "table_unit": resolved_unit,
                    "table_markdown": _truncate_table_markdown(table_markdown, max_chars=6000),
                },
            )
        except Exception:
            return []

        records: list[MetricRecord] = []
        for item in payload.get("metric_records") or []:
            if not isinstance(item, dict):
                continue
            raw_metric_name = str(item.get("metric_name", "")).strip()
            value = str(item.get("value", "")).strip()
            if not raw_metric_name or not value:
                continue
            # 与规则/pandas 路径保持一致：name 走归一化（去序号前缀 + 映射英文键），
            # label 保留 LLM 返回的原文（未返回则回退到未归一化的原始 name）。
            metric_name = self._normalizer.normalize(raw_metric_name)
            # 优先用模型返回的单位；未返回则用解析出的真实单位（绝不改写数值）。
            unit = str(item.get("unit") or resolved_unit).strip() or "元"
            records.append(MetricRecord(
                company_name=self._company_name,
                company_code=self._company_code,
                metric_name=metric_name,
                metric_label=str(item.get("metric_label") or raw_metric_name).strip(),
                time_scope=str(item.get("time_scope", "")).strip(),
                period_end=str(item.get("period_end") or period_end).strip(),
                value=value,
                unit=unit,
                currency="CNY",
                source_type="annual_report",
                source_document_id=self._source_document_id,
                source_table_id=table_id,
                source_caption=caption,
                confidence=str(item.get("confidence", "medium")).strip(),
                statement_type=statement_type,
                source_section=source_section,
            ))
        return records

    @staticmethod
    def _build_default_client():
        from finsight_agent.infra.llm.client import LlmClient
        return LlmClient(timeout_seconds=90, max_tokens=8192)


# ============================================================
# 辅助函数
# ============================================================

def _truncate_table_markdown(md: str, *, max_chars: int = 6000) -> str:
    """截断超长表格 markdown。"""
    if len(md) <= max_chars:
        return md
    return md[:max_chars] + "\n... [表格过长，已截断]"


def _infer_period_end(section_path: list[str], table_markdown: str) -> str:
    """从 section_path 或表格内容推断报告期末日期。"""
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", table_markdown)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return "2024-12-31"


def _infer_statement_type(caption: str, section_path: list[str]) -> str:
    """根据 caption 和 section_path 推断报表口径（fallback，当 elements 不可用时用）。

    判定规则：
    - 含"母公司" → parent_only
    - 含"合并" → consolidated
    - 无法判断 → unknown

    注意：MinerU 多数情况下不填充 caption_text / section_path，
    主路径应优先用 _build_statement_type_map 从 elements.jsonl 按页码识别。
    """
    text = caption + " " + " ".join(section_path)
    if "母公司" in text:
        return "parent_only"
    if "合并" in text:
        return "consolidated"
    return "unknown"


# 报表标题关键词（用于 elements.jsonl 标题识别）
_STATEMENT_KEYWORDS = (
    "资产负债表",
    "利润表",
    "现金流量表",
    "所有者权益变动表",
    "股东权益变动表",
)


def _build_statement_type_map(elements_path: Path) -> tuple[dict[int, str], set[int], dict[int, str]]:
    """从 elements.jsonl 构建 page → statement_type 映射，并返回注释区页码集合 + 注释章节标题。

    MinerU 不填充 tables.jsonl 的 caption_text/section_path，
    但 elements.jsonl 里有报表标题段落元素（如"1、合并资产负债表""5、公司资产负债表"）。

    判定规则：
    - 标题含"合并" + 报表关键词 → consolidated
    - 标题含报表关键词但不含"合并" → parent_only（母公司报表常省略"母"字，如"公司利润表"）
    - "财务报表主要项目注释"之后 → 注释区，记录每个注释章节标题

    注：MinerU 的 element_type 字段（不是 type），且注释章节标题的 element_type 是 paragraph
    而非 title。因此用正则识别注释章节标题（^\d+、模式），不依赖 element_type。

    返回：(page→statement_type 映射, 注释区页码集合, page→注释章节标题)
    第三个返回值用于 _extract_single_table 找最近章节标题，再查 LLM 决策。
    """
    if not elements_path.exists():
        return {}, set(), {}

    heading_entries: list[tuple[int, str]] = []  # (page, statement_type)
    notes_start_pages: list[int] = []  # 可能有多个注释区（合并注释 + 母公司注释）
    notes_section_titles: dict[int, str] = {}  # page → 注释章节标题

    # 注释章节标题模式：支持多种格式
    #   "1、货币资金"（比亚迪等） / "(1) 货币资金"（美的等） / "（1）货币资金"
    #   "9. 金融工具"（春秋航空/平安银行等，数字+点） / "10. 存货"
    notes_title_pattern = re.compile(r"^[\(（]?\d+[、\)）.]")

    with elements_path.open(encoding="utf-8") as f:
        in_notes_region = False
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            el = json.loads(stripped)
            text = str(el.get("text") or "").strip()
            page = int(el.get("page_start") or 0)
            if page <= 0:
                continue

            # 注释区开始：支持多种措辞
            #   "七、合并财务报表主要项目注释"（比亚迪）
            #   "四 合并财务报表项目附注"（美的）
            #   "七、 合并财务报表项目注释"（用友网络）
            #   "十九、公司财务报表主要项目注释"（比亚迪母公司）
            # 通用匹配：含"财务报表" + ("注释"或"附注") + 长度<30（排除正文句子）
            if "财务报表" in text and ("注释" in text or "项目附注" in text) and len(text) < 30:
                notes_start_pages.append(page)
                in_notes_region = True
                continue

            # 注释区内的章节标题（正则匹配，不依赖 element_type）
            # 模式如"1、货币资金""2、交易性金融资产""3、应收账款"
            if in_notes_region and notes_title_pattern.match(text):
                notes_section_titles[page] = text
                continue

            # 报表标题：含报表关键词（element_type 是 paragraph，不依赖 title 类型）
            if not any(kw in text for kw in _STATEMENT_KEYWORDS):
                continue

            if "合并" in text:
                heading_entries.append((page, "consolidated"))
            else:
                # 不含"合并"的报表标题 → 母公司（如"5、公司资产负债表"）
                heading_entries.append((page, "parent_only"))

    if not heading_entries and not notes_start_pages and not notes_section_titles:
        return {}, set(), {}

    heading_entries.sort(key=lambda x: x[0])
    notes_start_pages.sort()

    # 二次扫描：如果页面选择阶段漏掉了注释区起点标题页（如"七、合并财务报表项目附注"），
    # 导致 in_notes_region 从未激活、notes_section_titles 为空，
    # 但注释章节标题（如"5、应收账款"）在财务报表之后的页面存在，
    # 仍把它们识别为注释章节标题，让下面的兜底逻辑激活注释区。
    # 典型场景：海天味业 structured 目录缺 p95-p121（注释区起点页），
    # 但 p122/p133 有注释章节标题"5、应收账款""10、存货"。
    if not notes_start_pages and not notes_section_titles and heading_entries:
        last_stmt_page = heading_entries[-1][0]
        with elements_path.open(encoding="utf-8") as f2:
            for line2 in f2:
                stripped2 = line2.strip()
                if not stripped2:
                    continue
                el2 = json.loads(stripped2)
                text2 = str(el2.get("text") or "").strip()
                page2 = int(el2.get("page_start") or 0)
                if page2 <= last_stmt_page or not text2:
                    continue
                # 排除报表标题（含报表关键词的不算注释章节）
                if any(kw in text2 for kw in _STATEMENT_KEYWORDS):
                    continue
                if notes_title_pattern.match(text2) and len(text2) < 50:
                    notes_section_titles[page2] = text2
        if notes_section_titles:
            print(f"  [二次扫描] 注释区起点缺失，从财务报表后的注释章节标题检测到 "
                  f"{len(notes_section_titles)} 个 (p{min(notes_section_titles.keys())}+)", flush=True)

    # 兜底：如果 structured_pages 跳过了注释区起点标题页（如"七、合并财务报表项目附注"），
    # 但包含了注释章节标题（如"1、货币资金"），自动从第一个注释章节标题页激活注释区。
    # 这解决了 LLM 配页码时漏配注释区起点标题页的问题。
    if not notes_start_pages and notes_section_titles:
        fallback_start = min(notes_section_titles.keys())
        notes_start_pages.append(fallback_start)
        print(f"  [兜底] 注释区起点标题缺失，从注释章节标题 p{fallback_start} 自动激活注释区", flush=True)

    # 构建注释区页码集合：每个注释区起点 +300 页（覆盖整个注释区）
    notes_pages: set[int] = set()
    for start in notes_start_pages:
        for p in range(start, start + 300):
            notes_pages.add(p)

    # 构建 page → statement_type：每个标题的口径持续到下一个标题或注释区
    result: dict[int, str] = {}
    for i, (page, stype) in enumerate(heading_entries):
        next_page = heading_entries[i + 1][0] if i + 1 < len(heading_entries) else page + 200
        # 若注释区在本标题之后，截止到注释区开始
        end_page = next_page
        for ns in notes_start_pages:
            if ns > page:
                end_page = min(end_page, ns)
        for p in range(page, min(end_page, page + 200)):
            if p not in notes_pages:  # 注释区不标记 statement_type
                result[p] = stype

    return result, notes_pages, notes_section_titles


# ============================================================
# 注释章节 LLM 决策（keep/skip）
# ============================================================

# 懒加载 prompt 文件
_NOTES_SECTION_DECISION_PROMPT: str | None = None


def _load_notes_section_decision_prompt() -> str:
    """懒加载 notes_section_decision.txt prompt 文件。"""
    global _NOTES_SECTION_DECISION_PROMPT
    if _NOTES_SECTION_DECISION_PROMPT is None:
        prompt_path = Path(__file__).parent / "prompts" / "notes_section_decision.txt"
        _NOTES_SECTION_DECISION_PROMPT = prompt_path.read_text(encoding="utf-8")
    return _NOTES_SECTION_DECISION_PROMPT


def _decide_notes_sections_via_llm(
    llm_client,
    section_titles: list[str],
    company_code: str,
    cache_dir: Path,
) -> dict[str, int]:
    """用 LLM 判断注释章节是否值得入库，结果缓存到文件。

    Args:
        llm_client: LlmClient 实例（可为 None，此时保守跳过所有注释表）
        section_titles: 注释章节标题列表（如 ["1、货币资金", "5、应收账款"]）
        company_code: 公司代码（用于缓存文件名）
        cache_dir: 缓存目录（var/data/notes_section_decisions/）

    Returns:
        {title: keep_or_not} 字典，keep=1 入库，keep=0 跳过
    """
    if not section_titles:
        return {}

    cache_path = cache_dir / f"{company_code}.json"

    decisions: list[dict] = []
    from_cache = False

    # 1. 命中缓存直接复用（section_titles 列表一致才算命中）
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("section_titles") == section_titles:
                decisions = cached.get("decisions", [])
                from_cache = True
        except Exception:
            pass  # 缓存损坏，重新调 LLM

    # 2. 无缓存时调 LLM（无 LLM 则保守跳过）
    if not from_cache:
        if not llm_client:
            return {t: 0 for t in section_titles}

        # 分批调用（每批 30 个标题）：注释章节多时（如隆基 78 个），
        # decisions 列表的 JSON 会超过 max_tokens 被截断导致解析失败。
        try:
            system_prompt = _load_notes_section_decision_prompt()
            batch_size = 30
            for i in range(0, len(section_titles), batch_size):
                batch = section_titles[i : i + batch_size]
                result = llm_client.complete_json(
                    prompt_name="notes_section_decision",
                    variables={
                        "system_prompt": system_prompt,
                        "sections": json.dumps(batch, ensure_ascii=False),
                    },
                )
                batch_decisions = result.get("decisions", [])
                if isinstance(batch_decisions, list):
                    decisions.extend(d for d in batch_decisions if isinstance(d, dict))
        except Exception as e:
            print(f"  LLM 注释章节决策失败: {e}，保守跳过所有注释表", flush=True)
            return {t: 0 for t in section_titles}

        # 写缓存
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {"section_titles": section_titles, "decisions": decisions},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # 3. 构建 decision_map + 兜底（LLM 漏返回的 title 默认 keep=1，
    #    避免因 title 文本不匹配导致有价值注释表被误 skip）
    decision_map = {d["title"]: int(d.get("keep", 0)) for d in decisions if isinstance(d, dict)}
    for t in section_titles:
        if t not in decision_map:
            decision_map[t] = 1
    return decision_map


def _find_nearest_notes_title(
    page_start: int, notes_section_titles: dict[int, str],
) -> str | None:
    """找到 page_start 所属的最近注释章节标题（往前找最近一个标题）。"""
    if not notes_section_titles:
        return None
    prior = [(p, t) for p, t in notes_section_titles.items() if p <= page_start]
    if not prior:
        return None
    return max(prior, key=lambda x: x[0])[1]


def _infer_source_section(statement_type: str, caption: str, in_notes: bool) -> str:
    """推断 source_section 字段值。

    - 注释区 keep=1 → "notes"
    - 三表区根据 caption 推断具体表类型
    - 其他 → "unknown"
    """
    if in_notes:
        return "notes"
    text = caption or ""
    if "资产负债表" in text:
        return "balance_sheet"
    if "利润表" in text:
        return "income_statement"
    if "现金流量表" in text:
        return "cash_flow_statement"
    if "所有者权益变动表" in text or "股东权益变动表" in text:
        return "equity_statement"
    return "unknown"


# 表格内容特征关键词（用于 MinerU 漏标题时的兜底推断）
_CONTENT_KEYWORDS_INCOME = ("营业总收入", "营业收入", "营业总成本", "营业成本", "利润总额", "净利润")
_CONTENT_KEYWORDS_CASHFLOW = ("经营活动产生的现金流量", "投资活动产生的现金流量", "筹资活动产生的现金流量")
_CONTENT_KEYWORDS_BALANCE = ("流动资产合计", "非流动资产合计", "资产总计", "负债合计", "所有者权益合计", "股东权益合计")
_CONTENT_KEYWORDS_EQUITY = ("实收资本", "资本公积", "盈余公积", "未分配利润")


def _refine_section_by_content(
    source_section: str,
    statement_type: str,
    table_markdown: str,
    table_html: str,
) -> tuple[str, str | None]:
    """根据表格内容校验/修正 source_section 和 statement_type。

    MinerU 可能漏掉报表标题（如"合并利润表"），导致表格的 section_path
    被前一个标题污染（如标成"母公司资产负债表"），source_section 和
    statement_type 随之错误。

    用表格内容的特征关键词兜底：
    - 含"营业总收入"/"利润总额"等 → income_statement
    - 含"经营活动产生的现金流量"等 → cash_flow_statement
    - 含"资产总计"/"负债合计"等 → balance_sheet
    - 含"实收资本"/"资本公积"等 + "变动" → equity_statement

    当 source_section 被修正（说明 caption 被污染）时，statement_type
    也修正为 consolidated（MinerU 污染方向是合并表被标成母公司）。

    返回：(修正后的 source_section, 修正后的 statement_type 或 None)
    """
    content = (table_markdown or table_html)[:800]
    if not content.strip():
        return source_section, None

    is_income = any(kw in content for kw in _CONTENT_KEYWORDS_INCOME)
    is_cashflow = any(kw in content for kw in _CONTENT_KEYWORDS_CASHFLOW)
    is_balance = any(kw in content for kw in _CONTENT_KEYWORDS_BALANCE)
    is_equity = any(kw in content for kw in _CONTENT_KEYWORDS_EQUITY) and "变动" in content

    refined = source_section
    changed = False

    # 明确矛盾时覆盖：如 source_section='balance_sheet' 但内容是利润表
    if is_income and not is_cashflow and not is_balance:
        if source_section != "income_statement":
            refined = "income_statement"
            changed = True
    elif is_cashflow and not is_income and not is_balance:
        if source_section != "cash_flow_statement":
            refined = "cash_flow_statement"
            changed = True
    elif is_balance and not is_income and not is_cashflow:
        if source_section != "balance_sheet":
            refined = "balance_sheet"
            changed = True
    elif is_equity:
        if source_section != "equity_statement":
            refined = "equity_statement"
            changed = True

    # source_section 被修正 → caption 被污染 → statement_type 也修正为 consolidated
    # 污染模式：合并利润表被标成"母公司资产负债表"（继承前一个 title）
    if changed and statement_type == "parent_only":
        return refined, "consolidated"

    return refined, None


# LLM 回退用的 prompt（只在规则失败时用）
TABLE_EXTRACTOR_LLM_PROMPT = """你是金融财报表格分析专家。给定一张指标时间序列表（markdown 格式），提取每个指标每个期间的值。

输出JSON：
{
  "metric_records": [
    {
      "metric_name": "指标名",
      "time_scope": "期间标识（如'期末余额''2024年度'）",
      "period_end": "YYYY-MM-DD",
      "value": "数值字符串（保留原始格式）",
      "unit": "元",
      "confidence": "high"
    }
  ]
}

注意：
- value 保留原始字符串（含千分位逗号）
- 跳过纯分类行（如"流动资产:"）
- 跳过空值
- 只输出JSON对象
"""
