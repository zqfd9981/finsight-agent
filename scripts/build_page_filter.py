"""扫描 2025 年报 PDF，根据目录/书签提取值得检索的页面，输出到 JSON 文件。

策略：
  1. 优先读 PDF outline（书签），70% 的年报有
  2. 无 outline 时，提取目录页文本做正则解析
  3. 章节筛选支持两种模式：
     - 规则模式（默认）：按章节价值表 KEEP_PATTERNS / DROP_PATTERNS
     - LLM 模式（--use-llm）：把完整章节树喂给 LLM 决策，失败回退规则
  4. 财务报告章节过长时只取前 25 页（审计报告+三表+部分附注）

输出：var/data/page_filter/annual_2025_pages.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import pypdf

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "var" / "data" / "raw_filings"
OUTPUT_PATH = REPO_ROOT / "var" / "data" / "page_filter" / "annual_2025_pages.json"
BACKEND_SRC = REPO_ROOT / "backend" / "src"


# ============================================================
# 章节价值表：规则模式使用
# ============================================================

KEEP_PATTERNS = [
    (r"会计数据.*财务指标|主要财务数据|主要会计数据|财务指标摘要|财务概要|會計數據.*財務指標|主要財務數據|主要會計數據|財務指標摘要|財務摘要|財務資料摘要|財務與經營亮點|財務概要", "财务指标"),
    (r"管理层讨论|经营情况讨论|业务讨论与分析|经营情况分析|讨论与分析|管理層討論|經營情況討論|業務討論與分析|經營情況分析|討論與分析|董事長報告|行長報告|董事會報告", "MD&A"),
    (r"重要事项|重要事項", "重要事项"),
    (r"财务报告|財務報告", "财务报告"),
]

DROP_PATTERNS = [
    r"重要提示|释义|目录|备查文件|釋義|目錄|備查文件",
    r"公司治理",
    r"环境.*社会责任|環境.*社會責任",
    r"股份变动|股东情况|股份變動|股東情況",
    r"优先股|優先股",
    r"债券相关|債券相關",
    r"封面|目錄|釋義|公司簡介|公司資料|公司基本情況|致辭|大事記",
]

FINANCIAL_REPORT_PATTERN = r"财务报告|財務報告"
FINANCIAL_REPORT_KEEP_PAGES = 25

MIN_REAL_REPORT_PAGES = 50


# ============================================================
# outline 提取（保留完整树，含子章节）
# ============================================================

def extract_outline_tree(reader: pypdf.PdfReader) -> list[dict] | None:
    """从 PDF 书签提取完整章节树（含子章节）。

    返回结构：
    [
        {"title": "第一节 ...", "start_page": 2, "depth": 0, "children": [
            {"title": "一、...", "start_page": 3, "depth": 1, "children": []},
            ...
        ]},
        ...
    ]
    """
    outline = getattr(reader, "outline", None)
    if not outline:
        return None

    def walk(items, depth=0):
        nodes: list[dict] = []
        i = 0
        while i < len(items):
            item = items[i]
            if isinstance(item, list):
                # 子节点列表，归到上一个节点
                if nodes:
                    nodes[-1]["children"] = walk(item, depth + 1)
                i += 1
                continue
            try:
                page_idx = reader.get_destination_page_number(item)
                nodes.append({
                    "title": item.title.strip(),
                    "start_page": page_idx + 1,
                    "depth": depth,
                    "children": [],
                })
            except Exception:
                pass
            i += 1
        return nodes

    tree = walk(outline, 0)
    return tree if tree else None


def flatten_tree(tree: list[dict]) -> list[dict]:
    """把章节树扁平化，保留 depth 信息。"""
    flat: list[dict] = []

    def walk(nodes):
        for node in nodes:
            flat.append({
                "title": node["title"],
                "start_page": node["start_page"],
                "depth": node["depth"],
            })
            if node.get("children"):
                walk(node["children"])

    walk(tree)
    return flat


# ============================================================
# 目录页正则解析（放开子章节过滤，保留完整层级）
# ============================================================

TOC_LINE_PATTERN = re.compile(
    r"(.+?)\s*[·\.…•]{2,}\s*(\d{1,4})\s*$"
)

CHAPTER_PREFIX_PATTERN = re.compile(
    r"第([一二三四五六七八九十百]+)[章节]"
)

# 子章节编号模式：一、 / (一) / 1、 / 1.1 / 1.1.1 等
SUB_CHAPTER_PATTERNS = [
    re.compile(r"^[一二三四五六七八九十]+、"),
    re.compile(r"^[（(][一二三四五六七八九十]+[）)]"),
    re.compile(r"^\d+[、.]"),
    re.compile(r"^\d+\.\d"),
]


def find_toc_pages(pdf: pdfplumber.PDF, max_scan: int = 15) -> list[int]:
    toc_pages: list[int] = []
    for i, page in enumerate(pdf.pages[:max_scan]):
        text = page.extract_text() or ""
        if "目" in text and "录" in text:
            lines = text.split("\n")
            toc_lines = sum(1 for line in lines if TOC_LINE_PATTERN.search(line.strip()))
            if toc_lines >= 3:
                toc_pages.append(i + 1)
    return toc_pages


def parse_toc_text_detailed(text: str) -> list[dict]:
    """从目录页文本提取章节列表，保留层级信息。

    通过标题前缀判断层级：
    - "第X节/章" → depth 0
    - "一、" / "(一)" / "1、" / "1.1" → depth 1+
    """
    chapters: list[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = TOC_LINE_PATTERN.search(line)
        if not match:
            continue
        title = match.group(1).strip()
        printed_page = int(match.group(2))
        if len(title) < 2 or title.isdigit():
            continue

        depth = _infer_depth(title)
        chapters.append({"title": title, "printed_page": printed_page, "depth": depth})
    return chapters


def _infer_depth(title: str) -> int:
    """根据标题前缀推断层级。"""
    if CHAPTER_PREFIX_PATTERN.search(title):
        return 0
    for i, pattern in enumerate(SUB_CHAPTER_PATTERNS, start=1):
        if pattern.match(title):
            return i
    return 0


def detect_page_offset(
    pdf: pdfplumber.PDF,
    first_title: str,
    first_printed_page: int,
    max_scan: int = 20,
) -> int:
    search_key = first_title.replace(" ", "").replace("\u3000", "")
    if not search_key or len(search_key) < 2:
        return 0
    for i, page in enumerate(pdf.pages[:max_scan]):
        text = page.extract_text() or ""
        clean_text = text.replace(" ", "").replace("\u3000", "")
        if search_key in clean_text:
            return (i + 1) - first_printed_page
    return 0


def extract_toc_tree_from_text(pdf_path: Path) -> list[dict] | None:
    """从目录页文本提取章节树。返回嵌套结构或 None。"""
    with pdfplumber.open(str(pdf_path)) as pdf:
        toc_pages = find_toc_pages(pdf)
        if not toc_pages:
            return None

        toc_text = ""
        for page_num in toc_pages:
            page = pdf.pages[page_num - 1]
            toc_text += (page.extract_text() or "") + "\n"

        raw_chapters = parse_toc_text_detailed(toc_text)
        if not raw_chapters:
            return None

        first = raw_chapters[0]
        offset = detect_page_offset(pdf, first["title"], first["printed_page"])

        # 构建嵌套树
        flat: list[dict] = []
        for ch in raw_chapters:
            pdf_page = ch["printed_page"] + offset
            if pdf_page >= 1:
                flat.append({
                    "title": ch["title"],
                    "start_page": pdf_page,
                    "depth": ch["depth"],
                })
        if not flat:
            return None
        return _flat_to_tree(flat)


def _flat_to_tree(flat: list[dict]) -> list[dict]:
    """把扁平的章节列表（含 depth）转成嵌套树。"""
    if not flat:
        return []
    root: list[dict] = []
    stack: list[dict] = []
    for item in flat:
        node = {
            "title": item["title"],
            "start_page": item["start_page"],
            "depth": item["depth"],
            "children": [],
        }
        # 弹栈到合适的父节点
        while stack and stack[-1]["depth"] >= node["depth"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            root.append(node)
        stack.append(node)
    return root


# ============================================================
# 章节树规范化（修复7）：修正 outline 的结构混乱
# ============================================================

# 顶级章节前缀：第X节/第X章（depth=0）
TOP_CHAPTER_PATTERN = re.compile(r"^第[一二三四五六七八九十百]+[章节]")

# 子章节编号模式及其对应 depth
# 一、 → depth=1, (一) → depth=2, 1、 → depth=2, 1.1 → depth=3
SUB_CHAPTER_DEPTH_MAP = [
    (re.compile(r"^[一二三四五六七八九十]+、"), 1),
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 2),
    (re.compile(r"^\d+[、.]\s*\S"), 2),       # "1、" 或 "1." 后跟内容
    (re.compile(r"^\d+\.\d"), 3),              # "1.1" "3.2" 等
    (re.compile(r"^[（(]\d+[）)]"), 3),         # "(1)" "(2)" 等
    (re.compile(r"^\d+\)"), 3),                 # "1)" "2)" 等
]

# 非章节文本模式：这些应被剔除（表格行、孤立短语、序号无内容）
NON_CHAPTER_PATTERNS = [
    re.compile(r"^(年初余额|年末余额|本年计提|累计折旧|账面价值|原值：|合计|小计)\s*$"),
    re.compile(r"^(转至|固定资产转入|应付短期薪酬|应付设定提存|应付辞退福利)"),
    re.compile(r"^[（(][a-z][）)]\s*\S"),  # "(a)" "(b)" 等单字母标号
    re.compile(r"^[\d]+\s*$"),               # 纯数字
    re.compile(r"^(见附注)"),                  # "见附注四、13" 这种引用
    re.compile(r"^(组合中，按)"),              # "组合中，按账龄组合..." 表格子项
]

# 注释区起点关键词（用于识别合并/母公司注释区并加标记）
MERGED_NOTES_KEYWORDS = ("合并财务报表项目注释", "合并财务报表项目附注", "合并财务报表主要项目注释")
PARENT_NOTES_KEYWORDS = ("母公司财务报表项目注释", "母公司财务报表主要项目注释", "公司财务报表主要项目注释")


def _infer_normalized_depth(title: str, prev_depth: int) -> int | None:
    """根据标题前缀重新推断 depth。返回 None 表示无法判断（保留原 depth）。

    规则：
    - 第X节/第X章 → 0
    - 一、 → 1
    - (一) → 2
    - 1、/1. → 2
    - 1.1/1.2 → 3
    - (1)/1) → 3
    - 其他 → None（保留原 depth）
    """
    title = title.strip()
    if not title:
        return None
    if TOP_CHAPTER_PATTERN.match(title):
        return 0
    for pattern, depth in SUB_CHAPTER_DEPTH_MAP:
        if pattern.match(title):
            return depth
    return None


def _is_non_chapter_text(title: str) -> bool:
    """判断标题是否是非章节文本（表格行、孤立短语等），应剔除。"""
    title = title.strip()
    if not title or len(title) < 2:
        return True
    for pattern in NON_CHAPTER_PATTERNS:
        if pattern.match(title):
            return True
    return False


def _tag_notes_section(title: str) -> str:
    """给注释区起点标题加合并/母公司标记，便于 LLM 区分。"""
    if any(kw in title for kw in MERGED_NOTES_KEYWORDS):
        return f"[合并注释区] {title}"
    if any(kw in title for kw in PARENT_NOTES_KEYWORDS):
        return f"[母公司注释区] {title}"
    return title


def normalize_chapter_tree(tree: list[dict]) -> tuple[list[dict], list[str]]:
    """规范化章节树：修正 depth、剔除非章节文本、标记注释区。

    年报 PDF outline 常见混乱（修复7）：
    1. depth 全部为 0（平安银行：所有 "1.现金..." 都标 d0，实际应为 d1）
    2. 非章节文本被当成章节节点（平安："年初余额""合计"等表格行）
    3. 合并/母公司注释区同名子项无法区分（格力：都有 "1、应收账款"）

    本函数用纯规则修正，不调 LLM（避免额外成本）。

    返回 (规范化后的章节树, 修正说明列表)。
    """
    if not tree:
        return tree, []

    fixes: list[str] = []
    flat = flatten_tree(tree)
    if not flat:
        return tree, []

    # === 第1步：剔除非章节文本 ===
    cleaned: list[dict] = []
    removed_count = 0
    for node in flat:
        if _is_non_chapter_text(node["title"]):
            removed_count += 1
            continue
        cleaned.append(dict(node))
    if removed_count > 0:
        fixes.append(f"剔除非章节文本 {removed_count} 个")

    # === 第2步：重新推断 depth ===
    # 平安银行所有节点都是 d0，但 "1.现金..." 应是 d1，"(1)..." 应是 d2
    # 规则：若标题前缀匹配子章节模式，用推断的 depth；否则保留原 depth
    prev_depth = -1
    fixed_depth_count = 0
    for node in cleaned:
        new_depth = _infer_normalized_depth(node["title"], prev_depth)
        if new_depth is not None and new_depth != node["depth"]:
            node["depth"] = new_depth
            fixed_depth_count += 1
        prev_depth = node["depth"]
    if fixed_depth_count > 0:
        fixes.append(f"修正 depth {fixed_depth_count} 个")

    # === 第3步：修复孤立 depth=0 子项 ===
    # 场景：平安 "1.现金及存放中央银行款项" 被标 d0，但前缀 "1." 推断为 d2
    # 上一步已修正。但有些节点标题无标准前缀却被错标 d0（如 "审计报告" 在平安是 d0）
    # 规则：若节点标题无 "第X节" 前缀，且其前一个 d0 节点是 "第X章/第X节"，
    #       则此节点应为 d1（章节子项）
    chapter_pattern = re.compile(r"^第[一二三四五六七八九十百]+[章节]")
    for i, node in enumerate(cleaned):
        if node["depth"] == 0 and not chapter_pattern.match(node["title"]):
            # 检查是否在某个 "第X章" 之后
            has_parent_chapter = False
            for j in range(i - 1, -1, -1):
                if chapter_pattern.match(cleaned[j]["title"]):
                    has_parent_chapter = True
                    break
                if cleaned[j]["depth"] == 0 and chapter_pattern.match(cleaned[j]["title"]):
                    has_parent_chapter = True
                    break
            if has_parent_chapter:
                node["depth"] = 1
                # 不计入 fixed_depth_count（避免重复计数）

    # === 第4步：标记合并/母公司注释区 ===
    tagged_count = 0
    for node in cleaned:
        new_title = _tag_notes_section(node["title"])
        if new_title != node["title"]:
            node["title"] = new_title
            tagged_count += 1
    if tagged_count > 0:
        fixes.append(f"标记注释区 {tagged_count} 个")

    # === 第5步：重建嵌套树 ===
    normalized_tree = _flat_to_tree(cleaned)
    return normalized_tree, fixes


# ============================================================
# 章节区间构建
# ============================================================

def build_chapter_ranges_from_tree(
    tree: list[dict],
    total_pages: int,
) -> list[dict]:
    """把章节树扁平化并构建 (start, end) 区间。end = 下一章节 start - 1。

    保留 depth 信息，用于 LLM 决策。
    """
    flat = flatten_tree(tree)
    if not flat:
        return []

    sorted_chapters = sorted(flat, key=lambda c: c["start_page"])
    ranges: list[dict] = []
    for i, ch in enumerate(sorted_chapters):
        start = ch["start_page"]
        if i + 1 < len(sorted_chapters):
            end = sorted_chapters[i + 1]["start_page"] - 1
        else:
            end = total_pages
        if end < start:
            end = start
        ranges.append({
            "title": ch["title"],
            "start": start,
            "end": end,
            "page_count": end - start + 1,
            "depth": ch["depth"],
        })
    return ranges


def build_chapter_ranges_flat(chapters: list[dict], total_pages: int) -> list[dict]:
    """兼容旧接口：扁平章节列表构建区间。"""
    sorted_chapters = sorted(chapters, key=lambda c: c["start_page"])
    ranges: list[dict] = []
    for i, ch in enumerate(sorted_chapters):
        start = ch["start_page"]
        end = sorted_chapters[i + 1]["start_page"] - 1 if i + 1 < len(sorted_chapters) else total_pages
        if end < start:
            end = start
        ranges.append({
            "title": ch["title"],
            "start": start,
            "end": end,
            "page_count": end - start + 1,
            "depth": ch.get("depth", 0),
        })
    return ranges


# ============================================================
# 规则决策
# ============================================================

def match_any(title: str, patterns: list) -> str | None:
    for pattern, label in patterns:
        if re.search(pattern, title):
            return label
    return None


def match_drop(title: str) -> bool:
    for pattern in DROP_PATTERNS:
        if re.search(pattern, title):
            return True
    return False


def filter_pages_by_rule(chapter_ranges: list[dict]) -> list[dict]:
    """规则模式：按章节价值表筛选。只对 depth=0 的父章节决策。

    规则模式无法细分财务报告子章节，全部标 rag（LLM 模式才会区分 structured）。
    """
    kept: list[dict] = []

    for ch in chapter_ranges:
        title = ch["title"]
        # 子章节不单独决策（由父章节决定）
        if ch.get("depth", 0) > 0:
            continue

        if match_drop(title):
            continue

        label = match_any(title, KEEP_PATTERNS)
        if label:
            if re.search(FINANCIAL_REPORT_PATTERN, title) and ch["page_count"] > FINANCIAL_REPORT_KEEP_PAGES:
                kept.append({
                    "title": title,
                    "start": ch["start"],
                    "end": ch["start"] + FINANCIAL_REPORT_KEEP_PAGES - 1,
                    "page_count": FINANCIAL_REPORT_KEEP_PAGES,
                    "reason": f"{label}（只取前{FINANCIAL_REPORT_KEEP_PAGES}页）",
                    "processing_type": "rag",
                })
            else:
                kept.append({
                    "title": title,
                    "start": ch["start"],
                    "end": ch["end"],
                    "page_count": ch["page_count"],
                    "reason": label,
                    "processing_type": "rag",
                })
    return kept


# ============================================================
# LLM 决策
# ============================================================

LLM_SYSTEM_PROMPT = """你是金融文档分析专家，专长是A股上市公司年报结构分析。

任务：给定一份年报的完整章节树（含子章节和页码区间），决定哪些页码区间值得作为数据源，并标记处理路径。

【处理路径】每个保留区间必须标注 processing_type：
- "rag"：走RAG向量检索（文字型内容、语义查询场景）
- "structured"：走结构化指标库（表格型数据、精准数值查询场景）

【保留原则】
1. 必须保留4类核心内容（如果存在）：
   - 财务指标（主要会计数据、财务摘要、分季度数据、非经常性损益）→ rag
   - 管理层讨论与分析（MD&A，含行业格局、业务分析、风险因素）→ rag
   - 重要事项（诉讼、关联交易、承诺履行、资产处置）→ rag
   - 财务报告（审计报告+三表+部分重要附注）→ 分层处理见下

2. 财务报告章节必须细分到子区间，分别标注处理路径：
   - 审计报告（审计意见、关键审计事项）→ rag
   - 三表（资产负债表、利润表、现金流量表、所有者权益变动表）→ structured
   - 报表项目注释区（结构化数据核心来源，必须完整保留，不受页数限制）→ structured
     * 识别注释区起点标题：含"合并财务报表项目注释"/"合并财务报表项目附注"/"合并财务报表主要项目注释"的章节
     * 注释区起点必须独立输出一条 structured 区间，从起点页到下一个非注释大章节前
     * 母公司财务报表项目注释同样标 structured
     * 注释区起点标题页必须包含在 structured 区间内，否则下游无法识别注释区
   - 其他附注按价值筛选（必须保留以下高价值附注，不能全部丢弃）：
     * 会计政策/会计估计（收入确认、坏账计提等）→ rag
     * 关联方及关联交易 → rag（投资者高度关注，含关联交易明细、应收应付）
     * 承诺及或有事项 → rag
     * 资产负债表日后事项 → rag
     * 其他重要事项（债务重组、分部信息等）→ rag
     * 股份支付 → rag
     * 子公司清单、合并范围变动、外币项目、金融工具风险 → drop（直接不保留）
   - 其他章节（审计报告、会计政策、关联交易等 rag 内容）总页数控制在60页内

3. 合并章节（如"公司简介和主要财务指标"）只保留有检索价值的子区间
   - 如只保留"主要会计数据"那几页，丢弃工商信息、联系人

4. 丢弃低价值章节：公司治理、环境与社会责任、股份变动、优先股、债券相关、纯工商信息、致辞、大事记

5. MD&A章节如果异常长（>60页），可合理截断到前50页，在reason说明

【输出JSON格式】
{
  "kept_ranges": [
    {
      "start": 起始页码,
      "end": 结束页码,
      "title": "区间标题（父章节名或子章节名）",
      "reason": "保留理由",
      "processing_type": "rag" 或 "structured"
    }
  ]
}

【注意】
- start和end必须是PDF实际页码（1-based）
- 区间可以跨子章节
- 财务报告章节必须输出多个子区间（审计报告/三表/注释区/各类附注分别一条）
- 三表和报表项目注释区的processing_type必须是"structured"，审计报告和其他附注文字部分是"rag"
- 注释区是结构化数据的核心来源，绝不能漏标或只标个别子项；漏标注释区会导致下游90%的明细指标查询失败
- 不要输出markdown或多余文本，只输出JSON对象

【正确示例】某年报财务报告章节树含：
  - p142-p156 | 三表（资产负债表/利润表/现金流量表/所有者权益变动表）
  - p187-p244 | 七、合并财务报表主要项目注释
  - p277-p287 | 十九、公司财务报表主要项目注释
正确输出（注释区完整保留为 structured）：
  {"start":142,"end":156,"title":"财务报表（三表）","reason":"三表精准数值查询","processing_type":"structured"}
  {"start":187,"end":244,"title":"合并财务报表主要项目注释","reason":"注释区明细表结构化数据源","processing_type":"structured"}
  {"start":277,"end":287,"title":"公司财务报表主要项目注释","reason":"母公司注释区结构化数据源","processing_type":"structured"}

【错误示例】（绝对禁止）：
  - 只输出三表一条 structured，注释区完全漏标
  - 只挑"应收账款附注"等个别子项标 structured，其余注释区丢弃
  - 把注释区标成 rag（注释区是表格型数据，必须 structured）
"""


def filter_pages_by_llm(
    chapter_ranges: list[dict],
    company_key: str,
    total_pages: int,
    pdf_path: Path | None = None,
) -> tuple[list[dict], str]:
    """LLM 模式：把章节树喂给 LLM 决策。返回 (kept_ranges, source)。

    source 可能值：
    - "llm"：LLM 决策成功
    - "llm_fallback_rule"：LLM 失败，回退到规则
    """
    if not chapter_ranges:
        return [], "llm_fallback_rule"

    # 准备章节树文本（含子章节）
    tree_text = _format_chapter_tree_for_llm(chapter_ranges, total_pages)

    try:
        # 添加 backend/src 到 path 以导入 LlmClient
        if str(BACKEND_SRC) not in sys.path:
            sys.path.insert(0, str(BACKEND_SRC))
        from finsight_agent.infra.llm.client import LlmClient

        client = LlmClient(timeout_seconds=180, max_tokens=16384)
        payload = client.complete_json(
            prompt_name="chapter_selector",
            variables={
                "system_prompt": LLM_SYSTEM_PROMPT,
                "company_key": company_key,
                "total_pages": total_pages,
                "chapter_tree": tree_text,
            },
        )

        kept_ranges = _parse_llm_response(payload, chapter_ranges, total_pages)
        if kept_ranges:
            # 规则兜底：确保三表和注释区都被标为 structured（LLM 执行不稳定，可能漏标）
            kept_ranges, fixes = _ensure_financial_sections_structured(
                kept_ranges, chapter_ranges, total_pages, pdf_path
            )
            for fix in fixes:
                print(f"    [兜底补全] {company_key}: {fix}", flush=True)
            return kept_ranges, "llm"
        # LLM 返回空，回退规则
        return filter_pages_by_rule(chapter_ranges), "llm_fallback_rule"

    except Exception as exc:
        print(f"    [LLM失败] {company_key}: {type(exc).__name__}: {exc}", flush=True)
        return filter_pages_by_rule(chapter_ranges), "llm_fallback_rule"


def _format_chapter_tree_for_llm(chapter_ranges: list[dict], total_pages: int) -> str:
    """把章节区间列表格式化成 LLM 易读的缩进文本。

    为了控制 prompt 长度，只展示 depth<=1 的章节（父章节+一级子章节）。
    但注释区相关节点（含"财务报表项目注释"/"项目附注"等关键词）无论 depth 多深都必须展示，
    否则 LLM 看不到注释区起点，会把注释区漏标或标成 rag，导致下游 90% 明细查询失败。
    """
    # 注释区关键词：匹配注释区起点标题（不同公司写法不同）
    notes_keywords = ("项目注释", "项目附注", "财务报表项目")

    lines = [f"总页数: {total_pages}", "章节树:"]
    for ch in chapter_ranges:
        depth = ch.get("depth", 0)
        title = ch["title"]
        # depth>1 的节点默认折叠，但注释区相关节点必现
        is_notes_section = any(kw in title for kw in notes_keywords)
        if depth > 1 and not is_notes_section:
            continue
        indent = "  " * depth
        # 注释区节点加标记，提醒 LLM 注意
        marker = " [★注释区-必须structured]" if is_notes_section else ""
        lines.append(
            f"{indent}- p{ch['start']:>3}-{ch['end']:<3} ({ch['page_count']:>3}p) | {ch['title']}{marker}"
        )
    return "\n".join(lines)


def _parse_llm_response(
    payload: dict,
    chapter_ranges: list[dict],
    total_pages: int,
) -> list[dict]:
    """解析 LLM 返回的 kept_ranges，做合法性校验。"""
    raw_ranges = payload.get("kept_ranges") or []
    if not isinstance(raw_ranges, list):
        return []

    kept: list[dict] = []
    for item in raw_ranges:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("start", 0))
            end = int(item.get("end", 0))
        except (TypeError, ValueError):
            continue
        if start < 1 or end < start or start > total_pages:
            continue
        end = min(end, total_pages)
        # processing_type 校验：只接受 rag / structured，默认 rag
        ptype = str(item.get("processing_type", "rag")).strip().lower()
        if ptype not in ("rag", "structured"):
            ptype = "rag"
        kept.append({
            "title": str(item.get("title", "")).strip(),
            "start": start,
            "end": end,
            "page_count": end - start + 1,
            "reason": str(item.get("reason", "")).strip(),
            "processing_type": ptype,
        })
    # 按起始页排序
    kept.sort(key=lambda r: r["start"])
    return kept


# 注释区起点标题关键词（不同公司写法不同）
NOTES_SECTION_KEYWORDS = (
    "合并财务报表项目注释",
    "合并财务报表项目附注",
    "合并财务报表主要项目注释",
    "母公司财务报表项目注释",
    "母公司财务报表主要项目注释",
    "公司财务报表主要项目注释",
)

# 三表章节关键词：匹配"二、财务报表"等含三表的父章节
# 注意：用精确匹配避免误匹配"资产负债表日后事项"等
# 匹配规则：标题含"财务报表"但不含"编制基础"/"补充资料"/"分析"/"责任"等
STATEMENT_PARENT_KEYWORDS = ("财务报表",)
STATEMENT_EXCLUDE_KEYWORDS = (
    "编制基础",
    "补充资料",
    "分析",
    "责任",
    "审计",
    "项目附注",
    "项目注释",
    "主要项目注释",
    "折算",
    "合并范围",
    "编制方法",
    "范围的确定",
    "结构化主体",
    "未纳入",
)


def _ensure_financial_sections_structured(
    kept_ranges: list[dict],
    chapter_ranges: list[dict],
    total_pages: int,
    pdf_path: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """规则兜底：确保三表和注释区都被标为 structured。

    LLM 即使改了 prompt 也可能漏标（执行不稳定）：
    - 漏标注释区 → 下游 90% 明细查询失败
    - 漏标三表 → bs/is/cf 全部缺失（格力案例：LLM 只标了注释区，三表被漏）

    本函数扫描章节树，找三表和注释区章节，若 LLM 未标 structured 则自动补上。
    四层兜底：
      1. 三表兜底：章节树含"财务报表"父章节
      2. 注释区兜底：章节树含注释区起点标题
      3. 启发式兜底：章节树无三表节点但注释区已识别，前推15页
      4. 全文扫描兜底（修复9）：章节树"财务报告"start_page=0 且无子节点时，
         用 pdfplumber 扫描 PDF 找三表标题页和注释区起点

    返回 (修正后的 kept_ranges, 补充说明列表)。
    """
    if not chapter_ranges:
        return kept_ranges, []

    fixes: list[str] = []
    new_ranges: list[dict] = list(kept_ranges)

    # === 1. 三表兜底 ===
    # 找章节树中三表父章节（标题含"财务报表"但不含排除关键词，且页数>=3）
    # 典型：中国铝业"二、财务报表"depth=1 含三表；格力无此节点（三表不在章节树）
    # 页数下限 3 排除"5．合并财务报表"等 1 页的会计政策误匹配
    stmt_nodes: list[dict] = []
    for ch in chapter_ranges:
        title = ch["title"]
        if not any(kw in title for kw in STATEMENT_PARENT_KEYWORDS):
            continue
        # 排除"编制基础"/"补充资料"/"项目注释"等非三表章节
        if any(ex in title for ex in STATEMENT_EXCLUDE_KEYWORDS):
            continue
        # 页数下限：三表（合并+母公司四表）至少 3 页
        if ch.get("page_count", 0) < 3:
            continue
        stmt_nodes.append(ch)

    for stmt_node in stmt_nodes:
        start = stmt_node["start"]
        title = stmt_node["title"]

        # 计算三表章节结束页：下一个同级或更高级章节前
        end = total_pages
        stmt_depth = stmt_node.get("depth", 0)
        for ch in chapter_ranges:
            ch_start = ch["start"]
            ch_depth = ch.get("depth", 0)
            if ch_start <= start:
                continue
            if ch_depth <= stmt_depth:
                end = ch_start - 1
                break

        if end < start:
            end = start

        # 检查 LLM 是否已标这条为 structured
        already_structured = False
        for r in new_ranges:
            if r.get("processing_type") == "structured" and r["start"] <= start and r["end"] >= start:
                already_structured = True
                break

        if not already_structured:
            # 删除 LLM 错误标成 rag 且与三表重叠的区间
            new_ranges = [
                r for r in new_ranges
                if not (
                    r.get("processing_type") == "rag"
                    and r["start"] >= start
                    and r["end"] <= end
                )
            ]
            new_ranges.append({
                "title": title,
                "start": start,
                "end": end,
                "page_count": end - start + 1,
                "reason": "三表结构化数据源（规则兜底补全）",
                "processing_type": "structured",
            })
            fixes.append(
                f"补三表: p{start}-p{end} ({end-start+1}p) | {title}"
            )

    # === 2. 注释区兜底 ===
    notes_starts: list[dict] = []
    for ch in chapter_ranges:
        title = ch["title"]
        if any(kw in title for kw in NOTES_SECTION_KEYWORDS):
            notes_starts.append(ch)

    for notes_node in notes_starts:
        start = notes_node["start"]
        title = notes_node["title"]

        # 计算注释区结束页：下一个非注释大章节前
        end = total_pages
        notes_depth = notes_node.get("depth", 0)
        for ch in chapter_ranges:
            ch_start = ch["start"]
            ch_depth = ch.get("depth", 0)
            ch_title = ch["title"]
            if ch_start <= start:
                continue
            # 遇到同级或更高级的非注释章节，注释区结束
            if ch_depth <= notes_depth and not any(
                kw in ch_title for kw in NOTES_SECTION_KEYWORDS
            ):
                end = ch_start - 1
                break

        if end < start:
            end = start

        # 检查 LLM 是否已标这条为 structured
        already_structured = False
        for r in new_ranges:
            if r.get("processing_type") == "structured" and r["start"] <= start and r["end"] >= start:
                already_structured = True
                break

        if not already_structured:
            # 删除 LLM 错误标成 rag 且与注释区重叠的区间，避免重复
            new_ranges = [
                r for r in new_ranges
                if not (
                    r.get("processing_type") == "rag"
                    and r["start"] >= start
                    and r["end"] <= end
                )
            ]
            new_ranges.append({
                "title": title,
                "start": start,
                "end": end,
                "page_count": end - start + 1,
                "reason": "注释区明细表结构化数据源（规则兜底补全）",
                "processing_type": "structured",
            })
            fixes.append(
                f"补注释区: p{start}-p{end} ({end-start+1}p) | {title}"
            )

    if fixes:
        new_ranges.sort(key=lambda r: r["start"])

    # === 3. 三表缺失的启发式兜底 ===
    # 如果章节树没有三表节点（格力/平安案例：PDF outline 未给三表建书签），
    # 且注释区已识别，用注释区起点前 N 页作为三表区间。
    # 三表（资产负债表+利润表+现金流量表+权益变动表，合并+母公司）通常 10-20 页。
    # 判断"已有三表 structured"：区间页数>=5 且标题含"财务报表"但不含排除关键词
    # （排除"5．合并财务报表"等1页的会计政策误匹配）
    has_stmt_structured = False
    for r in new_ranges:
        if r.get("processing_type") != "structured":
            continue
        title = r.get("title", "")
        page_count = r.get("page_count", 0)
        if "财务报表" not in title:
            continue
        if any(ex in title for ex in STATEMENT_EXCLUDE_KEYWORDS):
            continue
        if page_count >= 5:  # 三表至少 5 页（合并+母公司四表）
            has_stmt_structured = True
            break

    if not has_stmt_structured:
        # 找最早的注释区起点
        notes_starts_pages = [
            ch["start"] for ch in chapter_ranges
            if any(kw in ch["title"] for kw in NOTES_SECTION_KEYWORDS)
        ]
        if notes_starts_pages:
            notes_start = min(notes_starts_pages)
            # 三表区间：注释区起点前 15 页（覆盖合并+母公司三表+权益变动表）
            stmt_start = max(1, notes_start - 15)
            stmt_end = notes_start - 1
            if stmt_end >= stmt_start:
                # 检查是否已被 structured 覆盖
                already_covered = False
                for r in new_ranges:
                    if (r.get("processing_type") == "structured"
                        and r["start"] <= stmt_start and r["end"] >= stmt_end):
                        already_covered = True
                        break
                if not already_covered:
                    # 删除与三表区间重叠的 rag
                    new_ranges = [
                        r for r in new_ranges
                        if not (
                            r.get("processing_type") == "rag"
                            and r["start"] >= stmt_start
                            and r["end"] <= stmt_end
                        )
                    ]
                    new_ranges.append({
                        "title": "财务报表（三表，启发式兜底）",
                        "start": stmt_start,
                        "end": stmt_end,
                        "page_count": stmt_end - stmt_start + 1,
                        "reason": "三表结构化数据源（章节树无三表节点，按注释区起点前推15页兜底）",
                        "processing_type": "structured",
                    })
                    fixes.append(
                        f"补三表(启发式): p{stmt_start}-p{stmt_end} ({stmt_end-stmt_start+1}p) | 注释区前推"
                    )
                    new_ranges.sort(key=lambda r: r["start"])

    # === 4. 全文扫描兜底（修复9） ===
    # 场景：PDF outline 有"第X节 财务报告"但 start_page=0 且无子节点，
    # 导致前三层兜底全不触发（中国联通/通威股份/海螺水泥/中国移动/兴业银行/交通银行/长城汽车）。
    # 修复：用 pdfplumber 扫描 PDF 找三表标题页和注释区起点标题页。
    # 只在 pdf_path 可用 且 当前 kept_ranges 无任何 structured 区间时触发。
    if pdf_path and not any(r.get("processing_type") == "structured" for r in new_ranges):
        scan_result = _scan_pdf_for_financial_sections(pdf_path, total_pages)
        if scan_result:
            stmt_start, stmt_end, notes_start, notes_end = scan_result
            # 删除与三表/注释区重叠的 rag 区间
            new_ranges = [
                r for r in new_ranges
                if not (
                    r.get("processing_type") == "rag"
                    and r["start"] >= stmt_start
                    and r["end"] <= (notes_end or stmt_end)
                )
            ]
            new_ranges.append({
                "title": "财务报表（三表，全文扫描兜底）",
                "start": stmt_start,
                "end": stmt_end,
                "page_count": stmt_end - stmt_start + 1,
                "reason": "三表结构化数据源（章节树无页码，全文扫描定位）",
                "processing_type": "structured",
            })
            fixes.append(
                f"补三表(全文扫描): p{stmt_start}-p{stmt_end} ({stmt_end-stmt_start+1}p)"
            )
            if notes_start and notes_end and notes_end > notes_start:
                new_ranges.append({
                    "title": "合并财务报表项目注释（全文扫描兜底）",
                    "start": notes_start,
                    "end": notes_end,
                    "page_count": notes_end - notes_start + 1,
                    "reason": "注释区明细表结构化数据源（全文扫描定位）",
                    "processing_type": "structured",
                })
                fixes.append(
                    f"补注释区(全文扫描): p{notes_start}-p{notes_end} ({notes_end-notes_start+1}p)"
                )
            new_ranges.sort(key=lambda r: r["start"])

    return new_ranges, fixes


# 三表标题正则（全文扫描兜底用）
_STMT_TITLE_RE = re.compile(
    r"^(合并|公司|母公司)?(资产负债表|利润表|现金流量表|所有者权益变动表|股东权益变动表)"
)
# 注释区起点正则
_NOTES_START_RE = re.compile(
    r"(合并|公司|母公司)?财务报表(项目注释|项目附注|主要项目注释)"
)


def _scan_pdf_for_financial_sections(
    pdf_path: Path,
    total_pages: int,
) -> tuple[int, int, int | None, int | None] | None:
    """全文扫描 PDF 找三表标题页和注释区起点页。

    返回 (stmt_start, stmt_end, notes_start, notes_end) 或 None。
    notes_start/notes_end 可能为 None（未找到注释区）。
    """
    import pdfplumber

    stmt_pages: list[int] = []
    notes_pages: list[int] = []

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            n_pages = len(pdf.pages)
            for i in range(n_pages):
                text = pdf.pages[i].extract_text() or ""
                if not text:
                    continue
                lines = text.split("\n")
                for line in lines[:5]:  # 标题在页首前5行
                    line = line.strip()
                    if not line:
                        continue
                    # 三表标题（排除"续"和目录页特征）
                    if _STMT_TITLE_RE.match(line) and "续" not in line and len(line) < 25:
                        # 排除"合并资产负债表日后事项"等非三表标题
                        if not any(x in line for x in ("日后", "分析", "摘要", "补充")):
                            stmt_pages.append(i + 1)
                    # 注释区起点
                    if _NOTES_START_RE.search(line) and len(line) < 35:
                        notes_pages.append(i + 1)
    except Exception:
        return None

    if not stmt_pages:
        return None

    stmt_start = min(stmt_pages)
    stmt_end = max(stmt_pages)

    # 注释区起点：取第一个不重复的（排除"续"页）
    notes_start = None
    notes_end = None
    if notes_pages:
        notes_start = min(notes_pages)
        notes_end = total_pages  # 注释区到PDF末尾

    return stmt_start, stmt_end, notes_start, notes_end


# ============================================================
# 主流程
# ============================================================

def process_pdf(pdf_path: Path, use_llm: bool = False) -> dict:
    """处理单个 PDF，返回筛选结果。"""
    result: dict = {
        "pdf_path": str(pdf_path.relative_to(REPO_ROOT)),
        "total_pages": 0,
        "source": "failed",
        "chapters": [],
        "kept_ranges": [],
        "kept_pages": [],
        "kept_page_count": 0,
        "compression_ratio": 0.0,
    }

    try:
        reader = pypdf.PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        result["total_pages"] = total_pages

        if total_pages < MIN_REAL_REPORT_PAGES:
            result["source"] = "skipped_too_short"
            return result

        # 1. 尝试 outline 树
        tree = extract_outline_tree(reader)
        if tree:
            base_source = "outline"
        else:
            # 2. 尝试目录页正则
            tree = extract_toc_tree_from_text(pdf_path)
            base_source = "toc_regex" if tree else None

        if not tree:
            result["source"] = "failed"
            return result

        # 修复7：规范化章节树（修正 depth、剔除非章节文本、标记注释区）
        tree, normalize_fixes = normalize_chapter_tree(tree)
        if normalize_fixes:
            result["normalize_fixes"] = normalize_fixes
            print(f"    [规范化] {pdf_path.parent.parent.parent.name}: {', '.join(normalize_fixes)}", flush=True)

        # 构建章节区间（扁平，含 depth）
        chapter_ranges = build_chapter_ranges_from_tree(tree, total_pages)
        result["chapters"] = [
            {
                "title": r["title"],
                "start": r["start"],
                "end": r["end"],
                "page_count": r["page_count"],
                "depth": r["depth"],
            }
            for r in chapter_ranges
        ]

        # 决策
        company_key = pdf_path.parent.parent.parent.name
        if use_llm:
            kept_ranges, source = filter_pages_by_llm(chapter_ranges, company_key, total_pages, pdf_path)
            result["source"] = source
        else:
            kept_ranges = filter_pages_by_rule(chapter_ranges)
            result["source"] = base_source

        kept_pages = ranges_to_pages(kept_ranges)

        result["kept_ranges"] = kept_ranges
        result["kept_pages"] = kept_pages
        result["kept_page_count"] = len(kept_pages)
        result["compression_ratio"] = round(len(kept_pages) / max(1, total_pages), 3)

    except Exception as exc:
        result["source"] = f"error: {type(exc).__name__}: {exc}"

    return result


def ranges_to_pages(ranges: list[dict]) -> list[int]:
    pages: list[int] = []
    for r in ranges:
        pages.extend(range(r["start"], r["end"] + 1))
    return sorted(set(pages))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="筛选2025年报PDF值得检索的页面")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="启用LLM决策模式（失败回退规则）",
    )
    parser.add_argument(
        "--company-code",
        type=str,
        default=None,
        help="只处理指定公司（如 601658 或 002129），支持逗号分隔多个（如 000651,002594）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="并行处理的公司数（默认 5，LLM 模式下显著加速）",
    )
    args = parser.parse_args()

    all_pdfs = sorted(RAW_ROOT.rglob("*.pdf"))
    annual_2025_pdfs = [
        p for p in all_pdfs
        if "/annual/" in p.as_posix().replace("\\", "/")
        and "annual_report_2025" in p.name
    ]
    if args.company_code:
        codes = [c.strip() for c in args.company_code.split(",") if c.strip()]
        annual_2025_pdfs = [
            p for p in annual_2025_pdfs
            if any(c in p.parent.parent.parent.name for c in codes)
        ]

    mode_label = "LLM决策" if args.use_llm else "规则模式"
    print(f"2025 年报 PDF: {len(annual_2025_pdfs)} 份 | 模式: {mode_label}")
    print("=" * 80, flush=True)

    documents: dict[str, dict] = {}
    source_counts: dict[str, int] = {}
    total_pages_all = 0
    kept_pages_all = 0

    # --company-code 模式下，先加载现有 JSON，保留未处理公司的记录
    if args.company_code and OUTPUT_PATH.exists():
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            documents = existing.get("documents", {})
            print(f"已加载现有 JSON: {len(documents)} 家公司（将只更新指定公司）")
        except Exception as exc:
            print(f"⚠️ 加载现有 JSON 失败，将全量重建: {exc}")
            documents = {}

    workers = max(1, min(args.workers, len(annual_2025_pdfs))) if annual_2025_pdfs else 1
    print(f"并行: {workers} workers")
    print("=" * 80, flush=True)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process_one(idx: int, pdf_path: Path) -> dict:
        return process_pdf(pdf_path, use_llm=args.use_llm)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_one, idx, pdf_path): (idx, pdf_path)
            for idx, pdf_path in enumerate(annual_2025_pdfs, 1)
        }
        for future in as_completed(futures):
            idx, pdf_path = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"[{idx:>3}/{len(annual_2025_pdfs)}] ✗ error: {type(exc).__name__}: {exc}", flush=True)
                continue
            company_key = pdf_path.parent.parent.parent.name
            rel_name = pdf_path.name
            # 同公司多份 PDF 时保留 kept_page_count 最多的（完整版而非摘要版）
            existing = documents.get(company_key)
            if existing and existing.get("kept_page_count", 0) >= result.get("kept_page_count", 0):
                print(f"    （保留已有记录 {existing.get('kept_page_count', 0)}p，跳过 {result.get('kept_page_count', 0)}p）", flush=True)
                continue
            documents[company_key] = result
            source = result["source"]
            source_counts[source] = source_counts.get(source, 0) + 1
            total_pages_all += result["total_pages"]
            kept_pages_all += result["kept_page_count"]
            status_icon = "✓" if result["kept_page_count"] > 0 else "✗"
            print(
                f"[{idx:>3}/{len(annual_2025_pdfs)}] {status_icon} {source:<18} | "
                f"{result['total_pages']:>3}p → {result['kept_page_count']:>3}p "
                f"({result['compression_ratio'] * 100:.0f}%) | {rel_name}",
                flush=True,
            )

    elapsed = time.time() - t0

    summary = {
        "total_pdfs": len(annual_2025_pdfs),
        "mode": "llm" if args.use_llm else "rule",
        "source_counts": source_counts,
        "total_pages": total_pages_all,
        "kept_pages": kept_pages_all,
        "compression_ratio": round(kept_pages_all / max(1, total_pages_all), 3),
        "elapsed_seconds": round(elapsed, 1),
    }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "documents": documents,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("汇总统计")
    print("=" * 80)
    print(f"  PDF 总数: {summary['total_pdfs']}")
    print(f"  模式: {mode_label}")
    print(f"  来源分布:")
    for src, cnt in sorted(source_counts.items()):
        print(f"    {src}: {cnt}")
    print(f"  总页数: {summary['total_pages']}")
    print(f"  保留页数: {summary['kept_pages']}")
    print(f"  压缩比: {summary['compression_ratio'] * 100:.1f}%")
    print(f"  耗时: {summary['elapsed_seconds']}s")
    print(f"\n  输出文件: {OUTPUT_PATH.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
