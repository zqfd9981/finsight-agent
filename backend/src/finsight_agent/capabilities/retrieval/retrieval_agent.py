"""自适应 RAG Agent：基于 LangGraph 状态图实现的检索循环。

流程：
    rewrite_query → hybrid_retrieve → reflect → ┬─ sufficient=true ──→ finalize
                                                  └─ sufficient=false, round<max ──→ 回到 rewrite_query
                                                     sufficient=false, round>=max ──→ finalize

LLM 只介入两个节点：
- rewrite_query: 把自然语言 query 改写为多个检索变体
- reflect: 评估证据充分度，决定是否重试

hybrid_retrieve 节点直接复用现有 RetrievalFacade（sparse + dense + RRF + rerank）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from finsight_agent.capabilities.retrieval.models import RetrievalResult
from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from finsight_agent.infra.llm.client import LlmClient

_logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# 在线 serving：2 轮反思足够。3 轮最坏 6 次串行 LLM（rewrite+reflect），
# 配合 30s timeout 单 stage 即可耗光 120s 前端预算。离线批处理可调高。
# LLM 慢时 2 轮可能累积超 180s（脚本/前端 timeout），可用
# FINSIGHT_RAG_MAX_ROUNDS=1 降级为单轮（仅 rewrite，无 reflect）。
_DEFAULT_MAX_ROUNDS = int(os.environ.get("FINSIGHT_RAG_MAX_ROUNDS", "2"))


class RetrievalAgentState(TypedDict, total=False):
    """LangGraph 状态对象，在节点间传递。"""

    # 输入（首轮由 invoke 注入）
    original_query: str
    intent: str
    entities: dict[str, Any]
    context_summary: str
    max_rounds: int
    retrieval_limit: int
    # router 解析出的目标公司（确定性公司对齐，不依赖 LLM 回填 company）
    target_company_code: str
    target_company_name: str

    # 每轮变化
    current_round: int
    rewrite_hint: str
    rewritten_queries: list[str]
    sub_questions: list[dict[str, Any]]
    rewrite_strategy: str

    # 检索结果
    retrieval_result: RetrievalResult
    all_evidence_items: list[dict[str, Any]]
    all_rewritten_queries: list[str]

    # reflect 输出
    sufficient: bool
    reflect_reason: str

    # 轨迹
    rounds_trace: list[dict[str, Any]]


@dataclass(slots=True, init=False)
class RetrievalAgent:
    """自适应 RAG Agent，封装 rewrite-retrieve-reflect 循环。

    用法：
        agent = RetrievalAgent(llm_client=..., retrieval_facade=...)
        result = agent.retrieve(original_query="...", intent="...", entities={...})
        # result.retrieval_result.evidence_items 即最终证据
    """

    _llm_client: LlmClient
    _retrieval_facade: RetrievalFacade
    _max_rounds: int = _DEFAULT_MAX_ROUNDS
    _query_rewrite_prompt: str = field(default_factory=lambda: _load_prompt("query_rewrite.txt"))
    _reflect_prompt: str = field(default_factory=lambda: _load_prompt("reflect.txt"))
    _compiled_graph: Any = field(default=None, repr=False)

    # dataclass 字段名带下划线前缀会导致构造参数名也带下划线
    # （_llm_client=... 而非 llm_client=...），与 docstring 和调用方不一致。
    # 因此用 init=False 禁用 dataclass 自动生成 __init__，手写无下划线参数名的构造函数。
    def __init__(  # noqa: PLR0913
        self,
        *,
        llm_client: LlmClient,
        retrieval_facade: RetrievalFacade,
        max_rounds: int = _DEFAULT_MAX_ROUNDS,
        query_rewrite_prompt: str | None = None,
        reflect_prompt: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._retrieval_facade = retrieval_facade
        self._max_rounds = max_rounds
        self._query_rewrite_prompt = (
            query_rewrite_prompt if query_rewrite_prompt is not None else _load_prompt("query_rewrite.txt")
        )
        self._reflect_prompt = (
            reflect_prompt if reflect_prompt is not None else _load_prompt("reflect.txt")
        )
        self._compiled_graph = self._build_graph().compile()

    def retrieve(
        self,
        *,
        original_query: str,
        intent: str = "",
        entities: dict[str, Any] | None = None,
        context_summary: str = "",
        retrieval_limit: int = 5,
        target_company_code: str = "",
        target_company_name: str = "",
    ) -> RetrievalAgentState:
        """执行自适应检索循环，返回最终状态。

        target_company_code / target_company_name：由 router 解析出的目标公司。
        用于确定性公司对齐——当 LLM 改写子问题未回填 company 字段时，
        仍对非 peer_reference 维度的子问题强制按目标公司过滤，避免跨公司噪声
        （如同业年报套话）混入。peer_reference 维度保持跨公司检索。
        """
        initial_state: RetrievalAgentState = {
            "original_query": original_query,
            "intent": intent,
            "entities": entities or {},
            "context_summary": context_summary,
            "max_rounds": self._max_rounds,
            "retrieval_limit": retrieval_limit,
            "target_company_code": target_company_code or "",
            "target_company_name": target_company_name or "",
            "current_round": 0,
            "rewrite_hint": "",
            "all_evidence_items": [],
            "all_rewritten_queries": [],
            "rounds_trace": [],
        }
        return self._compiled_graph.invoke(initial_state)

    def _build_graph(self) -> StateGraph:
        graph: StateGraph[RetrievalAgentState] = StateGraph(RetrievalAgentState)
        graph.add_node("rewrite_query", self._node_rewrite_query)
        graph.add_node("hybrid_retrieve", self._node_hybrid_retrieve)
        graph.add_node("reflect", self._node_reflect)
        graph.add_node("finalize", self._node_finalize)

        graph.set_entry_point("rewrite_query")
        graph.add_edge("rewrite_query", "hybrid_retrieve")
        graph.add_edge("hybrid_retrieve", "reflect")
        graph.add_conditional_edges(
            "reflect",
            self._should_retry,
            {
                "retry": "rewrite_query",
                "done": "finalize",
            },
        )
        graph.add_edge("finalize", END)
        return graph

    # ── 节点实现 ──────────────────────────────────────────────────

    def _node_rewrite_query(self, state: RetrievalAgentState) -> dict[str, Any]:
        """LLM 拆解 query 为多个分析子问题（兼容老的 rewritten_queries 格式）。"""
        current_round = state.get("current_round", 0) + 1
        try:
            payload = self._llm_client.complete_json(
                prompt_name="retrieval_query_rewrite",
                variables={
                    "system_prompt": self._query_rewrite_prompt,
                    "original_query": state["original_query"],
                    "intent": state.get("intent", ""),
                    "entities": state.get("entities", {}),
                    "context_summary": state.get("context_summary", ""),
                    "rewrite_hint": state.get("rewrite_hint", ""),
                },
            )
            sub_questions = payload.get("sub_questions") or []
            # 兼容老格式：rewritten_queries（纯字符串数组）
            if not sub_questions and payload.get("rewritten_queries"):
                sub_questions = [
                    {"query": str(q), "dimension": "", "company": "", "company_code": "", "focus": ""}
                    for q in payload["rewritten_queries"]
                ]
            if not isinstance(sub_questions, list) or not sub_questions:
                sub_questions = [{"query": state["original_query"], "dimension": "", "company": "", "company_code": "", "focus": ""}]
            normalized: list[dict[str, Any]] = []
            for sq in sub_questions:
                if not isinstance(sq, dict):
                    sq = {"query": str(sq), "dimension": "", "company": "", "company_code": "", "focus": ""}
                sq.setdefault("query", state["original_query"])
                sq.setdefault("dimension", "")
                sq.setdefault("company", "")
                sq.setdefault("company_code", "")
                sq.setdefault("focus", "")
                normalized.append(sq)
            strategy = str(payload.get("rewrite_strategy") or "")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query rewrite failed: %s; fallback to original", exc)
            normalized = [{"query": state["original_query"], "dimension": "", "company": "", "company_code": "", "focus": ""}]
            strategy = f"fallback: {type(exc).__name__}"

        # 兼容下游（reflect/finalize 仍消费字符串列表）
        rewritten_queries = [str(sq.get("query", "")) for sq in normalized]
        return {
            "current_round": current_round,
            "sub_questions": normalized,
            "rewritten_queries": rewritten_queries,
            "rewrite_strategy": strategy,
        }

    def _node_hybrid_retrieve(self, state: RetrievalAgentState) -> dict[str, Any]:
        """对每个分析子问题跑 RetrievalFacade，合并结果。

        性能优化：多个子问题并行检索（ThreadPoolExecutor）。
        bge-m3 embed 和 Qdrant query 都是线程安全的，SQLite FTS5 支持并发读。

        公司对齐过滤：对 direct_disclosure / financial_exposure 且指定了目标公司
        的子问题，仅保留目标公司证据，剔除异业噪声（竞品/无关行业年报套话）。
        peer_reference（不带公司）不过滤，单独成桶。
        """
        sub_questions = state.get("sub_questions") or [
            {"query": state["original_query"], "dimension": "", "company": "", "company_code": "", "focus": ""}
        ]
        limit = state.get("retrieval_limit", 5)
        # router 解析出的目标公司（确定性对齐来源）
        target_company_code = state.get("target_company_code", "") or ""
        target_company_name = state.get("target_company_name", "") or ""
        all_evidence = list(state.get("all_evidence_items", []))
        seen_evidence_ids: set[str] = {item.get("evidence_id", "") for item in all_evidence}
        latest_result: RetrievalResult | None = None

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _retrieve_one(sq: dict[str, Any]) -> tuple[RetrievalResult | None, list[dict[str, Any]]]:
            dimension = str(sq.get("dimension") or "").strip()
            is_peer = dimension == "peer_reference"
            try:
                # 非同业参照维度：用目标公司 code 做索引级硬过滤
                # （稀疏 FTS5 `company_code=?` + 稠密 Qdrant MatchValue），
                # 从检索源头排除跨公司噪声；peer_reference 维度保持跨公司。
                facade_company_code = (
                    target_company_code if (target_company_code and not is_peer) else None
                )
                result = self._retrieval_facade.retrieve_evidence(
                    raw_query=str(sq.get("query", "")),
                    limit=limit,
                    company_code=facade_company_code,
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("retrieve_evidence failed for %r: %s", sq.get("query"), exc)
                return None, []
            items = [_evidence_to_dict(e) for e in (result.evidence_items or [])]
            # 公司对齐过滤（双保险：索引硬过滤 + 结果级匹配）
            target = str(sq.get("company") or "").strip()
            # 兜底：LLM 未在子问题回填 company 时，用 router 目标公司做对齐，
            # 避免「天合光能年报」这类同业披露混入「隆基绿能」的检索结果。
            if not target and not is_peer and target_company_name:
                target = target_company_name
            if target and not is_peer:
                filtered = [e for e in items if _company_matches(e, target)]
                # 兜底：过滤后为空则保留原始结果，避免该子问题完全丢失证据
                items = filtered if filtered else items
            return result, items

        # 单子问题时直接同步调用，避免线程池开销
        if len(sub_questions) <= 1:
            retrieved = [_retrieve_one(sub_questions[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(sub_questions))) as executor:
                futures = {executor.submit(_retrieve_one, sq): sq for sq in sub_questions}
                retrieved = [future.result() for future in as_completed(futures)]

        for result, items in retrieved:
            if result is None:
                continue
            latest_result = result
            for evidence in items:
                eid = evidence.get("evidence_id", "")
                if eid and eid in seen_evidence_ids:
                    continue
                seen_evidence_ids.add(eid)
                all_evidence.append(evidence)

        if latest_result is None:
            latest_result = RetrievalResult(
                request_id="",
                normalized_claim=state["original_query"],
                evidence_items=[],
            )

        all_queries = list(state.get("all_rewritten_queries", []))
        all_queries.extend([str(sq.get("query", "")) for sq in sub_questions])

        round_trace = list(state.get("rounds_trace", []))
        round_trace.append({
            "round": state.get("current_round", 0),
            "sub_questions": [str(sq.get("query", "")) for sq in sub_questions],
            "evidence_count_this_round": len(all_evidence) - len(state.get("all_evidence_items", [])),
            "total_evidence_count": len(all_evidence),
        })

        return {
            "retrieval_result": latest_result,
            "all_evidence_items": all_evidence,
            "all_rewritten_queries": all_queries,
            "rounds_trace": round_trace,
        }

    def _node_reflect(self, state: RetrievalAgentState) -> dict[str, Any]:
        """LLM 评估证据充分度。

        异常处理策略：
        - LLM 调用或 JSON 解析失败时，默认 sufficient=False（继续重试），
          而非 sufficient=True（放弃），让回溯循环有机会在下一轮用原 query 重试。
          这样即使 LLM 偶发返回非法 JSON，也不会直接终止检索循环。
        - 重试由 _should_retry 的 round<max_rounds 条件控制，不会无限循环。
        """
        current_round = state.get("current_round", 1)
        max_rounds = state.get("max_rounds", self._max_rounds)

        # 收敛保护：连续两轮未检索到新增有效证据，提前终止，
        # 避免对「永不收敛」的 query 无限空转（仍受 max_rounds 硬上限兜底）。
        trace = state.get("rounds_trace", [])
        if len(trace) >= 2:
            prev_new = trace[-2].get("evidence_count_this_round", 0)
            curr_new = trace[-1].get("evidence_count_this_round", 0)
            if prev_new == 0 and curr_new == 0:
                _logger.info(
                    "retrieval convergence guard: 2 consecutive rounds with no new evidence, stop at round %d",
                    current_round,
                )
                return {
                    "sufficient": True,
                    "reflect_reason": "收敛保护：连续两轮未检索到新增有效证据，提前终止检索循环",
                    "rewrite_hint": "",
                }

        # 轮次用尽，强制结束
        if current_round >= max_rounds:
            return {
                "sufficient": True,
                "reflect_reason": f"已达到最大轮次 {max_rounds}，结束检索循环",
                "rewrite_hint": "",
            }

        evidence_items = state.get("all_evidence_items", [])
        if not evidence_items:
            return {
                "sufficient": False,
                "reflect_reason": "本轮未检索到任何证据",
                "rewrite_hint": "当前查询未召回证据，建议尝试更宽泛的关键词或补充相关实体名称",
            }

        try:
            payload = self._llm_client.complete_json(
                prompt_name="retrieval_reflect",
                variables={
                    "system_prompt": self._reflect_prompt,
                    "original_query": state["original_query"],
                    "intent": state.get("intent", ""),
                    "current_round": current_round,
                    "max_rounds": max_rounds,
                    "evidence_items": _truncate_evidence_for_reflect(evidence_items),
                    "evidence_count": len(evidence_items),
                    "rewritten_queries_used": state.get("rewritten_queries", []),
                },
            )
            sufficient = bool(payload.get("sufficient"))
            coverage = payload.get("coverage_adequate")
            reason = str(payload.get("reason") or "")
            # 覆盖不全时补充理由，便于排查拆解质量
            if coverage is False and not reason:
                reason = "子问题未覆盖关键分析维度（直接披露/财务敞口/同业参照）"
            rewrite_hint = str(payload.get("rewrite_hint") or "")
        except Exception as exc:  # noqa: BLE001
            # LLM 调用或 JSON 解析失败：直接终止回溯循环（sufficient=True）。
            # 之前默认 sufficient=False 会强制跑满 max_rounds，在 LLM 持续
            # 超时/异常时最坏 6 次串行 LLM，耗光 120s 前端预算。
            # 终止后用已检索到的 evidence 交给 synthesize，宁缺毋滥。
            _logger.warning(
                "reflect failed: %s; default to sufficient (terminate to avoid timeout)", exc
            )
            sufficient = True
            reason = f"reflect 异常，终止回溯避免超时: {type(exc).__name__}: {exc}"[:200]
            rewrite_hint = ""

        return {
            "sufficient": sufficient,
            "reflect_reason": reason,
            "rewrite_hint": rewrite_hint,
        }

    def _node_finalize(self, state: RetrievalAgentState) -> dict[str, Any]:
        """汇总最终结果。"""
        evidence_items = state.get("all_evidence_items", [])
        base_result = state.get("retrieval_result")

        if base_result is not None:
            # 用累积的证据替换最终结果
            from finsight_agent.capabilities.retrieval.models import (
                EvidenceItem,
                RetrievalResult as _RR,
                RetrievalTrace,
            )
            final_items = [_dict_to_evidence(item) for item in evidence_items[: state.get("retrieval_limit", 5)]]
            all_queries = state.get("all_rewritten_queries", [])
            trace = RetrievalTrace(
                original_query=state["original_query"],
                normalized_query=state["original_query"],
                rewrite_queries=all_queries,
                final_evidence_count=len(final_items),
            )
            final_result = _RR(
                request_id=base_result.request_id,
                normalized_claim=base_result.normalized_claim,
                evidence_items=final_items,
                retrieval_notes=base_result.retrieval_notes,
                retrieval_trace=trace,
            )
        else:
            final_result = RetrievalResult(
                request_id="",
                normalized_claim=state.get("original_query", ""),
                evidence_items=[],
            )

        return {"retrieval_result": final_result}

    # ── 条件边 ──────────────────────────────────────────────────

    def _should_retry(self, state: RetrievalAgentState) -> str:
        if state.get("sufficient"):
            return "done"
        current_round = state.get("current_round", 1)
        max_rounds = state.get("max_rounds", self._max_rounds)
        if current_round >= max_rounds:
            return "done"
        _logger.info(
            "retrieval agent retry: round=%d/%d, reason=%s",
            current_round,
            max_rounds,
            state.get("reflect_reason", ""),
        )
        return "retry"


# ── 工具函数 ──────────────────────────────────────────────────


def _load_prompt(filename: str) -> str:
    """优先用 PromptRegistry（集中 prompts/ 目录），回退到模块内 prompts/ 目录。"""
    # 1. 尝试 PromptRegistry：retrieval.{filename without .txt}
    dotted = f"retrieval.{filename.removesuffix('.txt')}"
    try:
        from finsight_agent.infra.llm.prompt_registry import get_prompt
        return get_prompt(dotted).text
    except Exception:
        pass
    # 2. 回退到模块内 prompts/ 目录
    path = _PROMPTS_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _evidence_to_dict(evidence: Any) -> dict[str, Any]:
    """把 EvidenceItem dataclass 转为 dict（用于状态传递）。"""
    if isinstance(evidence, dict):
        return evidence
    return {
        "evidence_id": getattr(evidence, "evidence_id", ""),
        "rank": getattr(evidence, "rank", 0),
        "excerpt": getattr(evidence, "excerpt", ""),
        "parent_context": getattr(evidence, "parent_context", ""),
        "company_code": getattr(evidence, "company_code", ""),
        "company_name": getattr(evidence, "company_name", ""),
        "doc_type": getattr(evidence, "doc_type", ""),
        "section_path": list(getattr(evidence, "section_path", []) or []),
        "matched_chunk_id": getattr(evidence, "matched_chunk_id", ""),
        "matched_parent_id": getattr(evidence, "matched_parent_id", ""),
    }


def _company_matches(evidence: dict[str, Any], target: str) -> bool:
    """判断证据是否属于目标公司（双向子串匹配，兼容简称/全称）。"""
    name = str(evidence.get("company_name") or "").strip()
    if not name:
        return False
    t = target.strip()
    return t in name or name in t


def _dict_to_evidence(item: dict[str, Any]) -> Any:
    """把 dict 转回 EvidenceItem。"""
    from finsight_agent.capabilities.retrieval.models import (
        CitationRecord,
        EvidenceItem,
        RetrievalScoreBreakdown,
    )
    return EvidenceItem(
        evidence_id=str(item.get("evidence_id", "")),
        rank=int(item.get("rank", 0)),
        support_strength=str(item.get("support_strength", "medium")),
        matched_chunk_id=str(item.get("matched_chunk_id", "")),
        matched_parent_id=item.get("matched_parent_id") or None,
        excerpt=str(item.get("excerpt", "")),
        parent_context=str(item.get("parent_context", "")),
        citation=CitationRecord(
            document_id=str(item.get("citation", {}).get("document_id", "")) if isinstance(item.get("citation"), dict) else "",
            page_start=int(item.get("citation", {}).get("page_start", 0)) if isinstance(item.get("citation"), dict) else 0,
            page_end=int(item.get("citation", {}).get("page_end", 0)) if isinstance(item.get("citation"), dict) else 0,
            page_anchor=item.get("citation", {}).get("page_anchor") if isinstance(item.get("citation"), dict) else None,
        ),
        retrieval_scores=RetrievalScoreBreakdown(),
        company_code=str(item.get("company_code", "")),
        company_name=str(item.get("company_name", "")),
        doc_type=str(item.get("doc_type", "")),
        section_path=list(item.get("section_path", []) or []),
    )


def _truncate_evidence_for_reflect(evidence_items: list[dict[str, Any]], max_items: int = 10) -> list[dict[str, Any]]:
    """reflect 时只传摘要，避免 token 过长。"""
    truncated = []
    for item in evidence_items[:max_items]:
        truncated.append({
            "evidence_id": item.get("evidence_id", ""),
            "excerpt": (item.get("excerpt", "") or "")[:200],
            "company_name": item.get("company_name", ""),
            "doc_type": item.get("doc_type", ""),
            "section_path": item.get("section_path", []),
        })
    return truncated
