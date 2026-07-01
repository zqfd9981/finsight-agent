from __future__ import annotations

from .acquisition_models import ClassifiedFiling, FilingRecord


def classify_filing(record: FilingRecord) -> ClassifiedFiling | None:
    """按标题做首版轻量分类，用于筛掉无关披露并归一化目标文档类型。"""

    title = record.title
    # 这几类通常不是我们要进入 RAG 语料库的正式主文档。
    if (
        "摘要" in title
        or "英文" in title
        or "取消" in title
        or "法律意见书" in title
        or "问询函回复" in title
        or "审核问询函" in title
        or "核查意见" in title
        or "独立财务顾问报告" in title
        or "会议资料" in title
        or "名单" in title
    ):
        return None

    # 半年度报告必须先判断，否则“年度报告”会把它误伤成 annual。
    if "半年度报告" in title or "半年报" in title:
        return ClassifiedFiling(normalized_doc_type="semiannual_report")
    if "年度报告" in title or title.endswith("年报"):
        return ClassifiedFiling(normalized_doc_type="annual_report")

    # 三类重要公告先做最小映射，后面再接更细的 source metadata 规则。
    if "业绩预告" in title or "业绩快报" in title:
        return ClassifiedFiling(
            normalized_doc_type="major_announcement",
            announcement_type="earnings_update",
        )
    if (
        "产能扩张" in title
        or "投资建设" in title
        or "重大合同" in title
        or "募投项目" in title
        or "增资以实施募投项目" in title
        or "共同投资" in title
        or "关联交易" in title
        or "向特定对象发行股票" in title
    ):
        return ClassifiedFiling(
            normalized_doc_type="major_announcement",
            announcement_type="capacity_expansion",
        )
    if (
        "并购" in title
        or "重组" in title
        or "股权激励" in title
        or "减值" in title
        or "回购公司股份" in title
        or "权益变动" in title
        or "持股5%以上" in title
    ):
        return ClassifiedFiling(
            normalized_doc_type="major_announcement",
            announcement_type="major_corporate_action",
        )
    return None
