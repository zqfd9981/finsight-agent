from __future__ import annotations

import io
import json
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from finsight_agent.capabilities.retrieval.parsing_models import (
    ParseReport,
    ParsedDocumentArtifact,
)
from finsight_agent.capabilities.retrieval.parsing_service import normalize_parsed_document

# 年报单位声明正则：匹配"单位：千元 / 单位为人民币万元 / 财务附注中报表的单位为：千元"等。
# 备选顺序必须长在前（百万元 > 千元 > 万元 > 元），避免"千元"被拆成"元"。
_UNIT_RE = re.compile(r"单位[：:为]?\s*(人民币)?\s*(?P<unit>百万元|千元|万元|元)")
# 命中"附注/notes"关键字的单位声明，视为仅约束注释表（不影响三表）。
_NOTES_SCOPE_RE = re.compile(r"附注|notes|财务报表附注", re.IGNORECASE)


def _resolve_unit_from_text(text: str) -> str | None:
    """从一段文本里解析'单位：X'式声明，返回 '元'/'千元'/'万元'/'百万元' 或 None。"""
    m = _UNIT_RE.search(text or "")
    if not m:
        return None
    return m.group("unit")


def _detect_table_unit(*texts: str) -> str | None:
    """从表格自身文本（caption/表体/表头/section）检测单位。

    覆盖两类来源：
      1) '单位：千元' 式声明（仍可能被 _resolve_unit_from_text 命中）；
      2) 列头里的 '(千元)' / '（万元）' 等括号单位（财务表常见写法）。
    优先匹配更具体的单位词（百万元>千元>万元），避免'千元'被'元'截断。
    仅用于单表判断，不更新全局状态。
    """
    blob = " ".join(t or "" for t in texts)
    if not blob:
        return None
    if "百万元" in blob:
        return "百万元"
    if "千元" in blob:
        return "千元"
    if "万元" in blob:
        return "万元"
    return None


class MineruDocumentParser:
    """基于 MinerU API 的主解析器。

    流程：
      1. POST /api/v4/file-urls/batch 申请上传链接（可带 page_ranges）
      2. PUT 上传 PDF 文件
      3. GET /api/v4/extract-results/batch/{batch_id} 轮询直到 state=done
      4. 下载 full_zip_url，解析 content_list.json 转成 ParsedDocumentArtifact

    支持通过 page_filter 指定解析页码（1-based），减少 API 额度消耗。
    """

    _API_BASE = "https://mineru.net/api/v4"
    _POLL_INTERVAL = 5  # 轮询间隔（秒）
    _MAX_POLL_WAIT = 600  # 最大等待（秒）

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_version: str = "vlm",
        cache_dir: str | Path | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("MINERU_API_KEY") or ""
        self._model_version = model_version
        self._cache_dir = Path(cache_dir) if cache_dir else None

    _PAGE_LIMIT = 200  # MinerU API 单次解析页数上限

    def parse(
        self,
        pdf_path: Path,
        page_filter: set[int] | None = None,
    ) -> ParsedDocumentArtifact:
        """解析单个 PDF，返回结构化解析产物。

        Args:
            pdf_path: PDF 文件路径
            page_filter: 只解析这些页码（1-based）。None 表示全量解析。
        """
        if not self._api_key:
            raise RuntimeError("missing mineru api key: set MINERU_API_KEY")

        pdf_size = pdf_path.stat().st_size
        if pdf_size > 200 * 1024 * 1024:
            raise ValueError(f"PDF too large ({pdf_size} bytes), MinerU limit is 200MB")

        # 检查 PDF 页数，超过 MinerU 200 页限制时自动物理拆分分批解析
        total_pages = _get_pdf_page_count(pdf_path)
        if total_pages <= self._PAGE_LIMIT:
            content_list, full_md = self._parse_single(pdf_path, page_filter)
        else:
            content_list, full_md = self._parse_large_pdf(
                pdf_path=pdf_path,
                total_pages=total_pages,
                page_filter=page_filter,
            )

        return _build_artifact(
            pdf_path=pdf_path,
            content_list=content_list,
            full_md=full_md,
            page_filter=page_filter,
        )

    def _parse_single(
        self,
        pdf_path: Path,
        page_filter: set[int] | None,
    ) -> tuple[list[list[dict]], str]:
        """单次解析（PDF 页数 ≤200）。"""
        page_ranges = _pages_to_ranges(page_filter)
        batch_id = self._upload_pdf(pdf_path=pdf_path, page_ranges=page_ranges)
        result_url = self._poll_batch_until_done(batch_id=batch_id)
        return self._download_and_extract_zip(
            result_url=result_url,
            cache_key=pdf_path.stem,
        )

    def _parse_large_pdf(
        self,
        pdf_path: Path,
        total_pages: int,
        page_filter: set[int] | None,
    ) -> tuple[list[list[dict]], str]:
        """对超过 200 页的 PDF 物理拆分分批解析，合并结果。

        MinerU API 限制单次 200 页（基于原始 PDF 页数，page_ranges 无效），
        因此用 PyMuPDF 拆分成多份临时 PDF，分别调 API，再按原始页码顺序合并。
        """
        import tempfile

        batch_size = self._PAGE_LIMIT
        # 确定需要解析的原始页码
        if page_filter:
            target_pages = sorted(page_filter)
        else:
            target_pages = list(range(1, total_pages + 1))

        # 按拆分批次分组（每批 ≤200 页，按原始页码归属）
        batches: list[tuple[int, list[int]]] = []  # (batch_start_page, [原始页码])
        for start in range(0, total_pages, batch_size):
            batch_range = set(range(start + 1, min(start + batch_size, total_pages) + 1))
            batch_pages = [p for p in target_pages if p in batch_range]
            if batch_pages:
                batches.append((start, batch_pages))

        print(f"    PDF {total_pages} 页超过 MinerU 200 页限制，拆分成 {len(batches)} 批解析", flush=True)

        page_to_content: dict[int, list[dict]] = {}
        all_full_mds: list[str] = []

        with tempfile.TemporaryDirectory(prefix="mineru_split_") as tmpdir:
            for batch_idx, (batch_start, batch_pages) in enumerate(batches, 1):
                batch_end = batch_start + batch_size  # 不含
                tmp_pdf = Path(tmpdir) / f"part_{batch_start}_{batch_end}.pdf"

                # 用 PyMuPDF 拆分 PDF
                _split_pdf(pdf_path, tmp_pdf, from_page=batch_start, to_page=batch_end - 1)

                # 映射原始页码 → 拆分后 PDF 的 1-based 页码，用 range 压缩格式
                split_pages = {p - batch_start for p in batch_pages}
                split_page_ranges = _pages_to_ranges(split_pages)

                print(f"    批次 {batch_idx}/{len(batches)}: 原始 p{batch_pages[0]}-{batch_pages[-1]} ({len(batch_pages)} 页)", flush=True)

                batch_id = self._upload_pdf(pdf_path=tmp_pdf, page_ranges=split_page_ranges)
                result_url = self._poll_batch_until_done(batch_id=batch_id)
                batch_content_list, batch_full_md = self._download_and_extract_zip(
                    result_url=result_url,
                    cache_key=f"{pdf_path.stem}_part{batch_idx}",
                )

                # 按 batch_pages 顺序映射回原始页码
                for idx, page_content in enumerate(batch_content_list):
                    if idx < len(batch_pages):
                        page_to_content[batch_pages[idx]] = page_content
                all_full_mds.append(batch_full_md)

        # 按 target_pages 顺序组装 content_list
        merged_content_list = [page_to_content.get(p, []) for p in target_pages]
        merged_full_md = "\n\n".join(all_full_mds)
        return merged_content_list, merged_full_md

    def _upload_pdf(
        self,
        *,
        pdf_path: Path,
        page_ranges: str | None,
    ) -> str:
        """申请上传链接 + PUT 上传文件。返回 batch_id。带 3 次重试。"""
        url = f"{self._API_BASE}/file-urls/batch"
        file_payload: dict[str, Any] = {"name": pdf_path.name}
        if page_ranges:
            file_payload["page_ranges"] = page_ranges

        body = {
            "files": [file_payload],
            "model_version": self._model_version,
            "enable_formula": True,
            "enable_table": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_err: Exception | None = None
        for attempt in range(3):
            if attempt > 0:
                wait = 10 * attempt
                print(f"    MinerU API 失败，{wait}s 后重试 (attempt {attempt + 1}/3)", flush=True)
                time.sleep(wait)
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("code") != 0:
                    raise RuntimeError(f"mineru apply upload url failed: {payload.get('msg')}")

                data = payload["data"]
                batch_id = data["batch_id"]
                upload_urls = data["file_urls"]
                if not upload_urls:
                    raise RuntimeError("mineru returned no upload url")

                with pdf_path.open("rb") as f:
                    put_resp = requests.put(upload_urls[0], data=f, timeout=300)
                    put_resp.raise_for_status()

                return batch_id
            except Exception as exc:
                last_err = exc
                # 网络错误或 API 临时错误都重试
                print(f"    MinerU upload 异常: {type(exc).__name__}: {exc}", flush=True)

        raise RuntimeError(f"mineru upload failed after 3 retries: {last_err}")

    def _poll_batch_until_done(self, *, batch_id: str) -> str:
        """轮询 batch 结果直到 state=done，返回 full_zip_url。"""
        url = f"{self._API_BASE}/extract-results/batch/{batch_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        deadline = time.time() + self._MAX_POLL_WAIT
        while time.time() < deadline:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise RuntimeError(f"mineru query batch failed: {payload.get('msg')}")

            results = payload.get("data", {}).get("extract_result") or []
            if not results:
                time.sleep(self._POLL_INTERVAL)
                continue

            item = results[0]
            state = item.get("state", "")

            if state == "done":
                full_zip_url = item.get("full_zip_url")
                if not full_zip_url:
                    raise RuntimeError(f"mineru done but no full_zip_url: {item}")
                return full_zip_url
            if state == "failed":
                err_msg = item.get("err_msg", "unknown")
                raise RuntimeError(f"mineru task failed: {err_msg}")

            time.sleep(self._POLL_INTERVAL)

        raise TimeoutError(f"mineru batch {batch_id} not done within {self._MAX_POLL_WAIT}s")

    def _download_and_extract_zip(
        self,
        *,
        result_url: str,
        cache_key: str,
    ) -> tuple[list[list[dict]], str]:
        """下载结果 zip，返回 (content_list, full_md)。"""
        resp = requests.get(result_url, timeout=120)
        resp.raise_for_status()

        content_list: list[list[dict]] = []
        full_md = ""

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            if self._cache_dir:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                zf.extractall(self._cache_dir / cache_key)

            for name in zf.namelist():
                if name.endswith("content_list.json"):
                    with zf.open(name) as f:
                        raw = json.loads(f.read().decode("utf-8"))
                    content_list = _normalize_content_list(raw)
                elif name.endswith("full.md"):
                    with zf.open(name) as f:
                        full_md = f.read().decode("utf-8")

        if not content_list:
            raise RuntimeError("mineru zip missing content_list.json")

        return content_list, full_md


# ============================================================
# 辅助函数
# ============================================================

def _get_pdf_page_count(pdf_path: Path) -> int:
    """用 PyMuPDF 获取 PDF 页数。"""
    import fitz
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count


def _split_pdf(src_path: Path, dst_path: Path, *, from_page: int, to_page: int) -> None:
    """用 PyMuPDF 从 src_path 提取 [from_page, to_page] 页（0-based）保存到 dst_path。"""
    import fitz
    doc = fitz.open(str(src_path))
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=from_page, to_page=to_page)
    new_doc.save(str(dst_path))
    new_doc.close()
    doc.close()


def _pages_to_ranges(page_filter: set[int] | None) -> str | None:
    """把页码集合转成 MinerU 的 page_ranges 格式，如 '2,4-6,8'。"""
    if not page_filter:
        return None
    pages = sorted(page_filter)
    if not pages:
        return None

    ranges: list[str] = []
    start = pages[0]
    prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = p
        prev = p
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ",".join(ranges)


def _normalize_content_list(raw: Any) -> list[list[dict]]:
    """把不同格式的 content_list 统一成 list[list[dict]]。

    MinerU 输出可能是：
    - list[list[dict]]：每页一个子列表（标准格式）
    - list[dict]：扁平列表，每个元素带 page_idx 字段
    """
    if not isinstance(raw, list):
        return []

    if raw and isinstance(raw[0], list):
        return [item for item in raw if isinstance(item, list)]

    by_page: dict[int, list[dict]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        page_idx = item.get("page_idx", 0)
        by_page.setdefault(int(page_idx), []).append(item)

    if not by_page:
        return []
    max_page = max(by_page.keys())
    return [by_page.get(i, []) for i in range(max_page + 1)]


# 报表标题关键词（三表 + 权益变动表）
_STMT_TITLE_KEYWORDS = ("资产负债表", "利润表", "现金流量表", "所有者权益变动表", "股东权益变动表")
# 注释区起点关键词
_NOTES_SECTION_KEYWORDS = ("财务报表主要项目注释", "合并财务报表项目附注", "公司财务报表主要项目注释", "财务报表附注")
# 注释章节标题模式："(1) 货币资金"、"1、货币资金"、"十四、应收账款" 等
_NOTES_CHAPTER_PATTERN = re.compile(r"^[\(（]?\d+[、\)）]\s*\S")
# 排除模式：长文本（>40 字）或含句号的句子不是标题
_TITLE_MAX_LEN = 40


def _is_likely_title(text: str) -> bool:
    """判断一段 text/paragraph 文本是否实际是标题（MinerU 未识别为 title 时的容错）。

    判定规则：
    1. 长度 ≤ 40 字（标题不会太长）
    2. 不含句号/分号（排除正文句子）
    3. 满足以下任一条件：
       a. 含三表关键词（资产负债表/利润表/现金流量表/权益变动表）
       b. 含注释区起点关键词（财务报表主要项目注释/合并财务报表项目附注等）
       c. 匹配注释章节标题模式（"(1) xxx" 或 "1、xxx" 开头）
    """
    if not text or len(text) > _TITLE_MAX_LEN:
        return False
    # 排除含句号/分号的正文句子
    if any(ch in text for ch in ("。", "；", "！", "？")):
        return False
    # 三表标题
    if any(kw in text for kw in _STMT_TITLE_KEYWORDS):
        return True
    # 注释区起点
    if any(kw in text for kw in _NOTES_SECTION_KEYWORDS):
        return True
    # 注释章节标题模式："(1) xxx" / "1、xxx" / "十四、xxx"
    if _NOTES_CHAPTER_PATTERN.match(text):
        return True
    return False


def _build_artifact(
    *,
    pdf_path: Path,
    content_list: list[list[dict]],
    full_md: str,
    page_filter: set[int] | None,
) -> ParsedDocumentArtifact:
    """把 MinerU 的 content_list 映射成 ParsedDocumentArtifact。"""
    elements: list[dict[str, object]] = []
    tables: list[dict[str, object]] = []
    current_section_path: list[str] = []
    table_index = 0
    # 单位解析状态：current_unit 为全局（三表）默认单位；notes_unit 为"仅注释表"单位。
    # 仅修正单位标签，绝不改写数值。
    current_unit: str = "元"
    notes_unit: str | None = None

    # content_list 是按页的列表，遍历时持续维护 current_section_path
    # 让后续 paragraph/table 元素继承最近一次 title 的 section_path
    for page_idx, page_elements in enumerate(content_list, start=1):
        if page_filter:
            sorted_pages = sorted(page_filter)
            if page_idx > len(sorted_pages):
                continue
            pdf_page = sorted_pages[page_idx - 1]
        else:
            pdf_page = page_idx

        for elem in page_elements:
            elem_type = str(elem.get("type", "text"))
            text = str(elem.get("text", "")).strip()
            # 单位声明解析（仅记录状态，绝不改写数值）：
            # 文本块里的"单位：千元/万元""财务附注中报表的单位为：千元"等。
            _decl_unit = _resolve_unit_from_text(text)
            if _decl_unit is not None:
                if _NOTES_SCOPE_RE.search(text):
                    notes_unit = _decl_unit  # 仅约束注释表
                else:
                    current_unit = _decl_unit  # 全局（三表）默认单位
            bbox = elem.get("bbox")
            # MinerU 常把报表标题/注释章节标题识别为 text/paragraph，
            # 这里基于文本模式提升为 title，让下游 TableExtractor 能识别章节边界
            if elem_type in ("text", "paragraph") and _is_likely_title(text):
                elem_type = "title"
            # 所有元素都继承当前 section_path（包括 title 自身）
            section_path_snapshot = list(current_section_path)

            if elem_type in ("title", "h1", "h2", "h3"):
                # 更新 section_path：用新标题替换同层级及更深的部分
                # 简化处理：直接用新标题作为当前 section
                current_section_path = [text]
                section_path_snapshot = list(current_section_path)
                elements.append({
                    "type": "title",
                    "page_start": pdf_page,
                    "page_end": pdf_page,
                    "text": text,
                    "section_path": section_path_snapshot,
                    "bbox": bbox,
                    "confidence": None,
                })
            elif elem_type == "table":
                table_index += 1
                table_body = elem.get("table_body") or elem.get("html") or ""
                table_caption = str(elem.get("table_caption") or elem.get("text") or "").strip()
                table_markdown = _html_to_markdown(table_body) if table_body else ""
                table_text = _strip_html(table_body) if table_body else text

                # 解析该表真实单位：优先用表自身文本（caption/表体/表头/section）检测到的单位
                # （覆盖"单位：千元"声明与列头"(千元)"两种写法）；注释表用 notes_unit；
                # 其余回退全局 current_unit。仅修正标签，绝不改写数值。
                _table_unit = _detect_table_unit(
                    table_caption, table_text, table_markdown, " ".join(section_path_snapshot)
                )
                if _table_unit:
                    resolved_unit = _table_unit
                elif ("附注" in section_path_snapshot or "附注" in table_caption) and notes_unit:
                    resolved_unit = notes_unit
                else:
                    resolved_unit = current_unit

                tables.append({
                    "page_start": pdf_page,
                    "page_end": pdf_page,
                    "section_path": section_path_snapshot,
                    "caption_text": table_caption,
                    "table_text": table_text,
                    "table_markdown": table_markdown,
                    "table_html": table_body,
                    "bbox": bbox,
                    "confidence": None,
                    "table_type_hint": "financial_statement",
                    "resolved_unit": resolved_unit,
                })
                elements.append({
                    "type": "table",
                    "page_start": pdf_page,
                    "page_end": pdf_page,
                    "text": table_text[:500],
                    "section_path": section_path_snapshot,
                    "bbox": bbox,
                    "confidence": None,
                    "related_table_id": f"{pdf_path.stem}_table_{table_index:06d}",
                })
            elif elem_type in ("text", "paragraph", "list", "image_caption", "footnote"):
                if not text:
                    continue
                elements.append({
                    "type": "paragraph",
                    "page_start": pdf_page,
                    "page_end": pdf_page,
                    "text": text,
                    "section_path": section_path_snapshot,
                    "bbox": bbox,
                    "confidence": None,
                })

    raw_payload = {
        "document": {
            "document_id": pdf_path.stem,
            "title": pdf_path.stem,
            "source_path": str(pdf_path),
            "page_count": len(content_list),
        },
        "elements": elements,
        "tables": tables,
        "parse_report": {
            "status": "success",
            "primary_parser": "mineru",
            "parser_version": "mineru_api_v4",
            "fallback_used": False,
            "warnings": [],
            "duration_ms": 0,
        },
    }
    return normalize_parsed_document(raw_payload=raw_payload, parser_source="mineru")


def _html_to_markdown(html: str) -> str:
    """简单 HTML 表格转 markdown 文本。"""
    if not html:
        return ""
    return _strip_html(html)


def _strip_html(html: str) -> str:
    """去掉 HTML 标签，保留文本。"""
    if not html:
        return ""
    text = re.sub(r"</tr>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</td>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"</th>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()
