"""检索公司对齐回归测试。

核心 bug：原先公司对齐完全依赖 LLM 在改写子问题里回填 company 字段，
LLM 没填就退化为跨全公司语义召回 → 查「隆基绿能」却返回大量「天合光能」。
修复后：router 解析出的目标公司确定性生效——

1. 非 peer_reference 子问题：retrieve_evidence 必须带 company_code 做索引级硬过滤；
2. peer_reference 子问题：保持跨公司（不带 company_code）；
3. LLM 未回填 company 时，仍用目标公司名做结果级对齐，剔除同业噪声。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.models import (
    CitationRecord,
    EvidenceItem,
    RetrievalResult,
    RetrievalScoreBreakdown,
    RetrievalTrace,
)
from finsight_agent.capabilities.retrieval.retrieval_agent import RetrievalAgent


def _make_evidence(company_name: str, company_code: str, eid: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=eid,
        rank=1,
        support_strength="medium",
        matched_chunk_id="",
        matched_parent_id=None,
        excerpt=f"{company_name} 关于红海航运风险的披露段落。",
        parent_context="",
        citation=CitationRecord(document_id="doc", page_start=1, page_end=2, page_anchor=1),
        retrieval_scores=RetrievalScoreBreakdown(),
        company_code=company_code,
        company_name=company_name,
        doc_type="_annual_",
        section_path=["风险"],
    )


class _FakeFacade:
    """记录 retrieve_evidence 调用，并返回混合公司名的证据。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def retrieve_evidence(self, *, raw_query: str, limit: int = 5, company_code: str | None = None, **_kw):
        self.calls.append({"query": raw_query, "limit": limit, "company_code": company_code})
        items = [
            _make_evidence("隆基绿能", "601012", "ev_longi_1"),
            _make_evidence("天合光能", "688599", "ev_trina_1"),
            _make_evidence("天合光能", "688599", "ev_trina_2"),
        ]
        return RetrievalResult(
            request_id="fake",
            normalized_claim=raw_query,
            evidence_items=items,
            retrieval_trace=RetrievalTrace(original_query=raw_query, normalized_query=raw_query),
        )


class _FakeLlm(SimpleNamespace):
    def __init__(self, sub_questions: list[dict[str, Any]]) -> None:
        self._sub_questions = sub_questions

    def complete_json(self, *, prompt_name: str, variables: dict[str, Any], **_kw):
        if prompt_name == "retrieval_query_rewrite":
            return {"sub_questions": self._sub_questions}
        if prompt_name == "retrieval_reflect":
            return {"sufficient": True, "reason": "test"}
        return {}


def _run_agent(sub_questions, target_code="601012", target_name="隆基绿能"):
    facade = _FakeFacade()
    llm = _FakeLlm(sub_questions)
    agent = RetrievalAgent(llm_client=llm, retrieval_facade=facade)
    state = agent.retrieve(
        original_query="红海局势会对隆基绿能产生什么影响",
        intent="event_impact_analysis",
        entities={"company": {"raw": "隆基绿能", "standard_name": "隆基绿能", "stock_code": "601012"}},
        retrieval_limit=4,
        target_company_code=target_code,
        target_company_name=target_name,
    )
    return facade, state


def test_direct_subquestion_gets_company_code_hard_filter():
    # LLM 未回填 company（这是出 bug 的场景）
    subs = [{"query": "红海 隆基绿能 航运 风险", "dimension": "direct_disclosure", "company": "", "company_code": "", "focus": ""}]
    facade, state = _run_agent(subs)
    assert facade.calls, "retrieve_evidence 未被调用"
    # 索引级硬过滤必须带上 company_code
    assert facade.calls[0]["company_code"] == "601012", facade.calls
    items = state["retrieval_result"].evidence_items
    names = {it.company_name for it in items}
    # 结果级对齐兜底：即便 LLM 没填 company，也只能剩目标公司
    assert names == {"隆基绿能"}, f"出现跨公司噪声: {names}"


def test_peer_reference_stays_cross_company():
    subs = [
        {"query": "光伏 红海 航运 同业影响", "dimension": "peer_reference", "company": "", "company_code": "", "focus": ""},
    ]
    facade, state = _run_agent(subs)
    # peer_reference 维度：故意不带 company_code（保持跨公司检索）
    assert facade.calls[0]["company_code"] is None, facade.calls
    # 同业参照允许返回竞品证据
    names = {it.company_name for it in state["retrieval_result"].evidence_items}
    assert "天合光能" in names, f"peer_reference 不应被过滤: {names}"


def test_no_target_company_keeps_cross_company():
    # 宏观/行业事件无目标公司：不应做任何公司过滤
    subs = [{"query": "红海 航运 光伏 行业影响", "dimension": "direct_disclosure", "company": "", "company_code": "", "focus": ""}]
    facade, state = _run_agent(subs, target_code="", target_name="")
    assert facade.calls[0]["company_code"] in (None, ""), facade.calls
    names = {it.company_name for it in state["retrieval_result"].evidence_items}
    assert "天合光能" in names, "无目标公司时不应过滤竞品"
