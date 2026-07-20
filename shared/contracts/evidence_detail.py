from __future__ import annotations

from typing import TypedDict

# 证据来源类型常量
SOURCE_TYPE_ANNUAL_REPORT = "annual_report"  # 年报 / 公告 RAG 检索片段
SOURCE_TYPE_FILING = "filing"  # 披露文件（与 annual_report 同源，按 doc_type 区分）
SOURCE_TYPE_NEWS = "news"  # 事件新闻（Bocha 外部检索）
SOURCE_TYPE_STRUCTURED_METRIC = "structured_metric"  # 年报结构化指标（数值）

# 来源类型 -> 前端展示用的中文标签 / 配色键
SOURCE_TYPE_LABELS: dict[str, str] = {
    SOURCE_TYPE_ANNUAL_REPORT: "年报 / 公告",
    SOURCE_TYPE_FILING: "披露文件",
    SOURCE_TYPE_NEWS: "事件新闻",
    SOURCE_TYPE_STRUCTURED_METRIC: "年报指标",
}


class EvidenceDetail(TypedDict):
    """统一证据溯源对象（跨 RAG / 事件新闻 / 结构化指标）。

    后端 builder 产出普通 dict（字段缺失时填空字符串 / 空列表），
    前端直接按 source_type 选择展示字段。所有字段均为可选展示字段，
    缺失不影响序列化。
    """

    evidence_id: str
    source_type: str
    # —— 公司 / 文档溯源（年报、公告、结构化指标通用）——
    company_name: str
    company_code: str
    doc_type: str
    report_year: str
    section_path: list[str]  # 章节路径，如 ["管理层讨论", "经营情况"]
    pages: str  # 页码标注，如 "p12-14"
    excerpt: str  # 原文摘录 / 片段
    support_strength: str  # 证据支持强度
    # —— 事件新闻专属 ——
    url: str  # 披露链接 / 新闻原文链接（如有）
    title: str  # 新闻标题
    publish_date: str  # 发布日期
    source: str  # 来源标识（bocha / 巨潮 等）
    # —— 结构化指标专属 ——
    metric: str
    value: str
    unit: str
    period: str
    matched_by: str
