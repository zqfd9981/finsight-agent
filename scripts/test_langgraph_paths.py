"""LangGraph 图拓扑路径验证（不依赖外部检索网络）。

验证 5 种 intent 的图路径正确性：
- metric_lookup → query_structured_data → synthesize_answer ✓
- general_finance_qa → synthesize_answer ✓
- out_of_scope → guardrail ✓
- event_impact_analysis 路径结构（mock 外部检索）
- evidence_lookup 路径结构

只验证图执行不报错 + stage 序列正确，不验证答案质量。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))

from shared.contracts.analysis_request import AnalysisRequest  # noqa: E402
from shared.contracts.router_result import RouterResult  # noqa: E402
from shared.enums.intent import Intent  # noqa: E402
from shared.enums.follow_up_type import FollowUpType  # noqa: E402

from finsight_agent.control_plane.orchestrator.service import (  # noqa: E402
    OrchestratorService,
)
from finsight_agent.control_plane.orchestrator.node_deps import (  # noqa: E402
    NodeDependencies,
    configure_dependencies,
)
from finsight_agent.control_plane.orchestrator.graph import build_graph  # noqa: E402
from finsight_agent.control_plane.orchestrator.state import OrchestratorState  # noqa: E402


def _build_mock_deps() -> NodeDependencies:
    """构建全 mock 依赖，避免触发真实 LLM/检索/嵌入。"""
    router_service = MagicMock()
    # 默认返回 general_finance_qa，具体测试会覆盖
    router_service.route.return_value = RouterResult(
        intent=Intent.GENERAL_FINANCE_QA.value,
        follow_up_type=FollowUpType.NONE.value,
        confidence="high",
        entities={},
        needs=[],
        constraints={},
    )
    structured_data_service = MagicMock()
    structured_data_service.query_metric_lookup.return_value = {
        "company": "测试公司",
        "metric": "revenue",
        "value": "1000000",
        "unit": "元",
        "time_scope": "2024",
        "is_degraded": False,
        "matched_by": "exact",
        "confidence": "high",
    }
    reporting_service = MagicMock()
    # build_response 返回一个简单的 mock 对象
    mock_response = MagicMock()
    mock_response.response_type = "success"
    mock_response.summary = "测试答案"
    reporting_service.build_response.return_value = mock_response

    retrieval_facade_factory = MagicMock(return_value=MagicMock())
    external_context_retriever = MagicMock()
    external_context_retriever.retrieve.return_value = {"event_context": {}, "source_status": {}}
    target_analysis_service = MagicMock()
    target_analysis_service.analyze.return_value = {
        "target_scope": [],
        "ranked_targets": [],
        "open_questions": [],
        "confidence": "low",
        "analysis_mode": "static",
    }
    session_service = MagicMock()
    session_service.load_context.return_value = None
    session_service.build_snapshot.return_value = None
    strategy_classifier = MagicMock()
    strategy_classifier.classify.return_value = {
        "strategy": "event_primary",
        "confidence": "low",
        "reason": "mock",
    }
    llm_client = MagicMock()

    return NodeDependencies(
        router_service=router_service,
        structured_data_service=structured_data_service,
        reporting_service=reporting_service,
        retrieval_facade_factory=retrieval_facade_factory,
        external_context_retriever=external_context_retriever,
        target_analysis_service=target_analysis_service,
        session_service=session_service,
        strategy_classifier=strategy_classifier,
        llm_client=llm_client,
    )


def _run_graph(
    deps: NodeDependencies,
    query: str,
    *,
    session_id: str = "",
) -> dict:
    """构建图并执行，返回 final_state。"""
    graph = build_graph(deps)
    initial_state: OrchestratorState = {
        "request": AnalysisRequest(
            query=query,
            query_mode="conversational",
            session_id=session_id,
            include_trace=True,
            notes=None,
        ),
        "session_context": None,
        "stage_observations": [],
    }
    return graph.invoke(initial_state)


def test_metric_lookup_path() -> None:
    """metric_lookup → query_structured_data → synthesize_answer。"""
    print("\n[TEST] metric_lookup 路径")
    deps = _build_mock_deps()
    deps.router_service.route.return_value = RouterResult(
        intent=Intent.METRIC_LOOKUP.value,
        follow_up_type=FollowUpType.NONE.value,
        confidence="high",
        entities={"company": "格力", "metric": "货币资金", "time_scope": "latest"},
        needs=["structured_data_query"],
        constraints={"preferred_output": "brief_answer"},
    )
    state = _run_graph(deps, "格力货币资金")
    assert state["router_result"].intent == "metric_lookup", f"intent mismatch: {state['router_result'].intent}"
    assert state["stages"] == ["query_structured_data", "synthesize_answer"], f"stages mismatch: {state['stages']}"
    assert state["response_mode"] == "brief_answer", f"response_mode mismatch: {state['response_mode']}"
    assert len(state["stage_observations"]) == 2, f"observations count: {len(state['stage_observations'])}"
    assert state["query_structured_data"] is not None
    assert state["synthesize_answer"] is not None
    assert state["final_response"] is not None
    assert len(state["trace_blocks"]) == 3  # routing + stage_planning + execution
    print("  [OK] metric_lookup 路径正确")


def test_general_finance_qa_path() -> None:
    """general_finance_qa → synthesize_answer。"""
    print("\n[TEST] general_finance_qa 路径")
    deps = _build_mock_deps()
    state = _run_graph(deps, "什么是市盈率")
    assert state["router_result"].intent == "general_finance_qa"
    assert state["stages"] == ["synthesize_answer"], f"stages mismatch: {state['stages']}"
    assert state["response_mode"] == "direct"
    assert len(state["stage_observations"]) == 1
    assert state["synthesize_answer"] is not None
    print("  [OK] general_finance_qa 路径正确")


def test_out_of_scope_guardrail_path() -> None:
    """out_of_scope → guardrail 短路。"""
    print("\n[TEST] out_of_scope guardrail 路径")
    deps = _build_mock_deps()
    deps.router_service.route.return_value = RouterResult(
        intent=Intent.OUT_OF_SCOPE.value,
        follow_up_type=FollowUpType.NONE.value,
        confidence="high",
        entities={},
        needs=[],
        constraints={"reason_code": "out_of_scope_request"},
    )
    state = _run_graph(deps, "今天天气怎么样")
    assert state["router_result"].intent == "out_of_scope"
    # out_of_scope 短路：guardrail_response 不为 None，无 final_response key
    assert state["guardrail_response"] is not None, "guardrail_response should not be None"
    assert state.get("final_response") is None, "final_response should be None for out_of_scope"
    # stages 为空（_build_out_of_scope_plan 返回 []）
    assert state.get("stages", []) == [], f"stages should be empty, got: {state.get('stages')}"
    print("  [OK] out_of_scope guardrail 路径正确")


def test_event_impact_analysis_path() -> None:
    """event_impact_analysis → collect_event_context → synthesize_answer (event_primary)。"""
    print("\n[TEST] event_impact_analysis (event_primary) 路径")
    deps = _build_mock_deps()
    deps.router_service.route.return_value = RouterResult(
        intent=Intent.EVENT_IMPACT_ANALYSIS.value,
        follow_up_type=FollowUpType.NONE.value,
        confidence="high",
        entities={"event": "美联储加息", "themes": ["银行股"], "time_scope": "recent"},
        needs=["event_context"],
        constraints={"time_hint": "recent"},
    )
    deps.strategy_classifier.classify.return_value = {
        "strategy": "event_primary",
        "confidence": "low",
        "reason": "mock",
    }
    # collect_event_context 需要 retrieval_facade，mock 它
    mock_facade = MagicMock()
    mock_facade.retrieve_evidence.return_value = MagicMock(evidence_items=[], query="test")
    deps.retrieval_facade_factory.return_value = mock_facade

    state = _run_graph(deps, "美联储加息对银行股的影响")
    assert state["router_result"].intent == "event_impact_analysis"
    assert state["stages"] == ["collect_event_context", "synthesize_answer"], f"stages: {state['stages']}"
    assert state["response_mode"] == "event_answer"
    assert len(state["stage_observations"]) == 2
    assert state["collect_event_context"] is not None
    print("  [OK] event_impact_analysis (event_primary) 路径正确")


def test_trace_blocks_structure() -> None:
    """验证 trace_blocks 包含 routing + stage_planning + execution 三个 block。"""
    print("\n[TEST] trace_blocks 结构")
    deps = _build_mock_deps()
    state = _run_graph(deps, "什么是市盈率")
    block_types = [b.block_type for b in state["trace_blocks"]]
    assert block_types == ["routing", "stage_planning", "execution"], f"block types: {block_types}"
    # routing block
    routing_block = state["trace_blocks"][0]
    assert routing_block.payload_summary["intent"] == "general_finance_qa"
    # stage_planning block
    planning_block = state["trace_blocks"][1]
    assert planning_block.payload_summary["stage_count"] == 1
    assert planning_block.payload_summary["response_mode"] == "direct"
    # execution block
    exec_block = state["trace_blocks"][2]
    assert exec_block.block_type == "execution"
    print("  [OK] trace_blocks 结构正确")


def main() -> None:
    tests = [
        test_metric_lookup_path,
        test_general_finance_qa_path,
        test_out_of_scope_guardrail_path,
        test_event_impact_analysis_path,
        test_trace_blocks_structure,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test_fn.__name__}: {exc}")
            import traceback

            traceback.print_exc()
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"结果: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 50}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
