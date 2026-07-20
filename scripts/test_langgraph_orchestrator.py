"""LangGraph orchestrator 集成测试脚本。

用法：
    set FINSIGHT_USE_LANGGRAPH_ORCHESTRATOR=1
    python scripts/test_langgraph_orchestrator.py

测试用例覆盖 4 种 response_mode：
- metric_lookup（结构化数据查询）
- general_finance_qa（LLM 直答）
- event_impact_analysis（事件影响分析）
- out_of_scope（guardrail 短路）
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))

from shared.contracts.analysis_request import AnalysisRequest  # noqa: E402

from finsight_agent.control_plane.orchestrator.service import (  # noqa: E402
    OrchestratorService,
)
from finsight_agent.control_plane.router.service import RouterService  # noqa: E402
from finsight_agent.control_plane.session.service import SessionService  # noqa: E402
from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (  # noqa: E402
    StubRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (  # noqa: E402
    TrainedRetrievalStrategyClassifier,
)


def build_service() -> OrchestratorService:
    return OrchestratorService()


def build_strategy_classifier():
    return TrainedRetrievalStrategyClassifier(
        fallback=StubRetrievalStrategyClassifier(),
    )


def run_test(query: str, *, label: str, include_trace: bool = True) -> None:
    print(f"\n{'=' * 70}")
    print(f"[TEST] {label}")
    print(f"  query: {query}")
    print(f"{'=' * 70}")

    service = build_service()
    router_service = RouterService()
    session_service = SessionService()
    classifier = build_strategy_classifier()

    request = AnalysisRequest(
        query=query,
        query_mode="conversational",
        session_id="",
        include_trace=include_trace,
        notes=None,
    )

    try:
        result = service.execute_graph(
            request=request,
            session_context=None,
            event_callback=None,
            router_service=router_service,
            session_service=session_service,
            strategy_classifier=classifier,
        )
        print(f"  intent: {result.router_result.intent if result.router_result else 'N/A'}")
        print(f"  stages: {result.stages}")
        print(f"  response_mode: {result.response_mode}")
        print(f"  stage_observations count: {len(result.stage_observations)}")
        print(f"  has final_response: {result.final_response is not None}")
        print(f"  has guardrail_response: {result.guardrail_response is not None}")
        print(f"  trace_blocks count: {len(result.trace_blocks)}")
        for obs in result.stage_observations:
            print(f"    - stage={obs.stage_name} status={obs.status}")
        if result.final_response:
            summary = getattr(result.final_response, "summary", "") or ""
            print(f"  final summary: {summary[:200]}")
        if result.guardrail_response:
            print(f"  guardrail reason: {result.guardrail_response.reason_code}")
        print(f"  [OK] {label}")
    except Exception as exc:
        print(f"  [FAIL] {label}: {exc}")
        import traceback

        traceback.print_exc()


def main() -> None:
    # 测试用例覆盖 4 种 response_mode + guardrail 短路
    tests = [
        ("格力电器货币资金", "metric_lookup", "metric_lookup"),
        ("宁德时代2024年归母净利润是多少", "metric_lookup 归母净利润", "metric_lookup"),
        ("什么是市盈率", "general_finance_qa", "general_finance_qa"),
        ("美联储加息对银行股的影响", "event_impact_analysis", "event_impact_analysis"),
        ("今天天气怎么样", "out_of_scope guardrail", "out_of_scope"),
    ]
    for query, label, _tag in tests:
        run_test(query, label=label)


if __name__ == "__main__":
    main()
