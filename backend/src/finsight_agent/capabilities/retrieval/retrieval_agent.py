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
_DEFAULT_MAX_ROUNDS = 3  # 完整回溯循环（配合并行检索优化性能）


class RetrievalAgentState(TypedDict, total=False):
    """LangGraph 状态对象，在节点间传递。"""

    # 输入（首轮由 invoke 注入）
    original_query: str
    intent: str
    entities: dict[str, Any]
    context_summary: str
    max_rounds: int
    retrieval_limit: int

    # 每轮变化
    current_round: int
    rewrite_hint: str
    rewritten_queries: list[str]
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
    ) -> RetrievalAgentState:
        """执行自适应检索循环，返回最终状态。"""
        initial_state: RetrievalAgentState = {
            "original_query": original_query,
            "intent": intent,
            "entities": entities or {},
            "context_summary": context_summary,
            "max_rounds": self._max_rounds,
            "retrieval_limit": retrieval_limit,
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
        """LLM 改写 query，生成多个检索变体。"""
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
            rewritten = payload.get("rewritten_queries") or []
            if not isinstance(rewritten, list) or not rewritten:
                rewritten = [state["original_query"]]
            strategy = str(payload.get("rewrite_strategy") or "")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("query rewrite failed: %s; fallback to original", exc)
            rewritten = [state["original_query"]]
            strategy = f"fallback: {type(exc).__name__}"

        return {
            "current_round": current_round,
            "rewritten_queries": [str(q) for q in rewritten],
            "rewrite_strategy": strategy,
        }

    def _node_hybrid_retrieve(self, state: RetrievalAgentState) -> dict[str, Any]:
        """对每个改写变体跑 RetrievalFacade，合并结果。

        性能优化：多个改写变体并行检索（ThreadPoolExecutor）。
        bge-m3 embed 和 Qdrant query 都是线程安全的，SQLite FTS5 支持并发读。
        """
        rewritten_queries = state.get("rewritten_queries") or [state["original_query"]]
        limit = state.get("retrieval_limit", 5)
        all_evidence = list(state.get("all_evidence_items", []))
        seen_evidence_ids: set[str] = {item.get("evidence_id", "") for item in all_evidence}
        latest_result: RetrievalResult | None = None

        # 并行检索多个变体
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _retrieve_one(query_variant: str) -> RetrievalResult | None:
            try:
                return self._retrieval_facade.retrieve_evidence(
                    raw_query=query_variant,
                    limit=limit,
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("retrieve_evidence failed for variant %r: %s", query_variant, exc)
                return None

        # 单变体时直接同步调用，避免线程池开销
        if len(rewritten_queries) <= 1:
            results = [_retrieve_one(rewritten_queries[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(rewritten_queries))) as executor:
                futures = {executor.submit(_retrieve_one, q): q for q in rewritten_queries}
                results = [future.result() for future in as_completed(futures)]

        for result in results:
            if result is None:
                continue
            latest_result = result
            for evidence in result.evidence_items:
                evidence_dict = _evidence_to_dict(evidence)
                eid = evidence_dict.get("evidence_id", "")
                if eid and eid in seen_evidence_ids:
                    continue
                seen_evidence_ids.add(eid)
                all_evidence.append(evidence_dict)

        if latest_result is None:
            latest_result = RetrievalResult(
                request_id="",
                normalized_claim=state["original_query"],
                evidence_items=[],
            )

        all_queries = list(state.get("all_rewritten_queries", []))
        all_queries.extend(rewritten_queries)

        round_trace = list(state.get("rounds_trace", []))
        round_trace.append({
            "round": state.get("current_round", 0),
            "rewritten_queries": rewritten_queries,
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
            reason = str(payload.get("reason") or "")
            rewrite_hint = str(payload.get("rewrite_hint") or "")
        except Exception as exc:  # noqa: BLE001
            # LLM 调用或 JSON 解析失败：默认继续重试（sufficient=False），
            # 让回溯循环有机会在下一轮用原 query 或新改写重试。
            # 只有 round >= max_rounds 时才会被 _should_retry 终止。
            _logger.warning(
                "reflect failed: %s; default to insufficient (will retry)", exc
            )
            sufficient = False
            reason = f"reflect 异常，默认继续重试: {type(exc).__name__}: {exc}"[:200]
            rewrite_hint = "上一轮 reflect 评估失败，建议尝试不同的改写策略"

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
