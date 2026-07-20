"""LangGraph StateGraph：orchestrator 全流程图定义。

把 router → strategy_classifier → stage_planner → stage 执行 → trace 组装 →
session 快照的全流程建模为 LangGraph StateGraph。每个处理步骤都是节点，
State 在节点间显式流转，条件边表达动态分支。

图结构：
    START → load_session → route ─┬─ out_of_scope ───────────→ guardrail → build_trace → save_snapshot → END
                                ├─ event_impact_analysis ──→ classify_strategy → plan_stages ─┐
                                └─ 其他 intent ─────────────→ plan_stages ───────────────────┤
                                                                                            ↓
                                                                              [stage链] → build_trace → save_snapshot → END

classify_strategy 仅对 event_impact_analysis 实际产出策略，其余意图在 route 后直接分流到
plan_stages（不再经过 classify_strategy 空过）。stage 链由 plan_stages 输出的 stages 列表
驱动，条件边按列表顺序串联。
"""

from __future__ import annotations

import functools
import logging
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from finsight_agent.config.feature_flags import setup_langsmith_tracing
from finsight_agent.control_plane.router.service import RouterService
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.shared.utils.execution_events import (
    RunEventEmitter,
    get_active_run_event_emitter,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.trace_block import TraceBlock
from shared.enums.intent import Intent
from shared.enums.response_type import ResponseType
from shared.enums.stage_name import StageName

from .models import OrchestrationResult, StageExecutionResult
from .node_deps import NodeDependencies, configure_dependencies, get_dependencies
from .observation_builder import build_stage_observation
from .policies import build_guardrail_response, should_short_circuit
from .stage_planner import build_plan, resolve_stages
from .stage_runners import (
    run_analyze_targets_stage,
    run_collect_event_context_stage,
    run_query_structured_data_stage,
    run_reflect_and_requery_stage,
    run_retrieve_evidence_stage,
    run_synthesize_answer_stage,
    run_verify_answer_stage,
)
from .state import OrchestratorState
from .trace_builder import build_execution_trace_block

_logger = logging.getLogger(__name__)

# LangGraph 节点名 → 对外 SSE stage 名映射
_NODE_TO_STAGE_NAME: dict[str, str] = {
    "load_session": "session_loading",
    "route": "routing",
    "plan_stages": "stage_planning",
    "guardrail": "guardrail",
    "query_structured_data": StageName.QUERY_STRUCTURED_DATA.value,
    "collect_event_context": StageName.COLLECT_EVENT_CONTEXT.value,
    "analyze_targets": StageName.ANALYZE_TARGETS.value,
    "retrieve_evidence": StageName.RETRIEVE_EVIDENCE.value,
    "synthesize_answer": StageName.SYNTHESIZE_ANSWER.value,
    "reflect_and_requery": StageName.REFLECT_AND_REQUERY.value,
    "verify_answer": StageName.VERIFY_ANSWER.value,
    "build_trace": "trace_building",
    "save_snapshot": "snapshot_saving",
}


# ──────────────────────────────────────────────────────────────────
# 节点函数：每个节点是 (state) -> partial_state 的纯函数
# ──────────────────────────────────────────────────────────────────


def _append_observation(
    state: OrchestratorState,
    stage_result: StageExecutionResult,
    *,
    input_summary: dict[str, Any] | None = None,
) -> list:
    """把 stage_result 包装成 StageObservation 并追加到 state.stage_observations。"""
    observation = build_stage_observation(
        observation_id=f"obs_{uuid.uuid4().hex[:8]}",
        input_summary=input_summary or {},
        stage_result=stage_result,
    )
    return list(state.get("stage_observations", []) or []) + [observation]


def _emit_stage_started(emitter: RunEventEmitter | None, node_name: str) -> str | None:
    """节点开始时 emit started 事件（方案 B：节点内部手动 emit）。"""
    if emitter is None:
        return None
    stage_name = _NODE_TO_STAGE_NAME.get(node_name, node_name)
    return emitter.emit_stage_started(
        stage_name=stage_name,
        message=f"{stage_name} started",
    )


def _emit_stage_finished(
    emitter: RunEventEmitter | None,
    node_name: str,
    started_at: str | None,
    stage_result: StageExecutionResult | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """节点结束时 emit finished 事件。"""
    if emitter is None:
        return
    stage_name = _NODE_TO_STAGE_NAME.get(node_name, node_name)
    status = "success"
    message = f"{stage_name} finished"
    if stage_result is not None:
        status = str(stage_result.status or "success")
        if stage_result.degraded_reason:
            message = stage_result.degraded_reason
        elif stage_result.user_summary:
            message = stage_result.user_summary
    final_payload: dict[str, Any] = {}
    if stage_result is not None:
        final_payload["evidence_ref_count"] = len(stage_result.evidence_refs)
        if stage_result.degraded_reason:
            final_payload["degraded_reason"] = stage_result.degraded_reason
        if "final_response" in stage_result.output_payload:
            final_payload["has_final_response"] = True
    if payload:
        final_payload.update(payload)
    emitter.emit_stage_finished(
        stage_name=stage_name,
        status=status,
        message=message,
        started_at=started_at,
        payload=final_payload,
    )


def load_session_node(state: OrchestratorState) -> dict:
    """加载会话上下文。"""
    deps = get_dependencies()
    emitter = get_active_run_event_emitter()
    started_at = _emit_stage_started(emitter, "load_session")
    try:
        session_context = deps.session_service.load_context(
            state["request"].session_id
        )
        _emit_stage_finished(emitter, "load_session", started_at)
        return {"session_context": session_context}
    except Exception as exc:
        _emit_stage_finished(emitter, "load_session", started_at)
        _logger.warning("load_session 失败，继续以空上下文执行: %s", exc)
        return {"session_context": None}


def route_node(state: OrchestratorState) -> dict:
    """路由节点：调用 RouterService，输出 router_result。"""
    deps = get_dependencies()
    emitter = get_active_run_event_emitter()
    started_at = _emit_stage_started(emitter, "route")
    try:
        router_result = deps.router_service.route(
            query=state["request"].query,
            session_context=state.get("session_context"),
        )
        _emit_stage_finished(
            emitter,
            "route",
            started_at,
            payload={
                "intent": router_result.intent,
                "follow_up_type": router_result.follow_up_type,
                "confidence": router_result.confidence,
            },
        )
        return {"router_result": router_result}
    except Exception as exc:
        _emit_stage_finished(emitter, "route", started_at)
        raise


# classify_strategy_node 已合并进 plan_stages_node（见 stage_planner.build_plan）：
# 对 event_impact_analysis 意图在 build_plan 内部完成策略三分类。


def plan_stages_node(state: OrchestratorState) -> dict:
    """阶段规划节点（单一入口）：内部完成 event 策略分类 + 查表规划。"""
    emitter = get_active_run_event_emitter()
    router_result = state["router_result"]
    started_at = _emit_stage_started(emitter, "plan_stages")
    try:
        deps = get_dependencies()
        session_context = state.get("session_context")
        session_topic = ""
        if session_context is not None:
            session_topic = str(session_context.active_topic or "").strip()

        # event 意图：先发射 strategy_classification 事件，保持与原 classify_strategy
        # 节点一致的可见性（分类已在 build_plan 内部完成）。
        is_event = router_result.intent == Intent.EVENT_IMPACT_ANALYSIS.value
        classify_started_at = None
        if is_event:
            classify_started_at = _emit_stage_started(emitter, "classify_strategy")

        stages, stage_constraints, response_mode, strategy_payload = build_plan(
            router_result,
            strategy_classifier=deps.strategy_classifier,
            query=state["request"].query,
            session_topic=session_topic,
        )

        if is_event:
            _emit_stage_finished(
                emitter,
                "classify_strategy",
                classify_started_at,
                payload=strategy_payload or {},
            )

        _emit_stage_finished(
            emitter,
            "plan_stages",
            started_at,
            payload={
                "intent": router_result.intent,
                "stages": list(stages),
                "response_mode": response_mode,
                "strategy": (
                    strategy_payload.get("strategy", "")
                    if strategy_payload
                    else ""
                ),
            },
        )
        return {
            "stages": stages,
            "stage_constraints": stage_constraints,
            "response_mode": response_mode,
            "strategy_payload": strategy_payload,
        }
    except Exception as exc:
        _emit_stage_finished(emitter, "plan_stages", started_at)
        raise


def guardrail_node(state: OrchestratorState) -> dict:
    """out_of_scope 短路节点：直接产出 guardrail_response。"""
    router_result = state["router_result"]
    emitter = get_active_run_event_emitter()
    started_at = _emit_stage_started(emitter, "guardrail")
    guardrail_response = build_guardrail_response(
        reason_code=router_result.constraints.get(
            "reason_code",
            "out_of_scope_request",
        ),
        progress_state="routing",
        partial_answer="当前请求超出 V1 支持范围，未进入常规执行流程。",
    )
    _emit_stage_finished(emitter, "guardrail", started_at)
    return {"guardrail_response": guardrail_response}


def _make_stage_node(
    node_name: str,
    runner: Callable,
    *,
    requires_session_context: bool = False,
    resolve_retrieval_facade: bool = False,
    requires_llm_client: bool = False,
    requires_external_context_retriever: bool = False,
    requires_target_analysis_service: bool = False,
    requires_structured_data_service: bool = False,
    requires_reporting_service: bool = False,
) -> Callable[[OrchestratorState], dict]:
    """通用 stage 节点工厂：包装 stage_runner，处理依赖注入、observation、SSE 事件。

    通过闭包捕获 node_name 和 runner，生成符合 LangGraph 节点签名的函数。
    """

    def node_fn(state: OrchestratorState) -> dict:
        deps = get_dependencies()
        emitter = get_active_run_event_emitter()
        started_at = _emit_stage_started(emitter, node_name)
        try:
            runner_kwargs: dict[str, Any] = {
                "request": state["request"],
                "router_result": state["router_result"],
                "execution_state": state,  # 兼容旧接口（stage_runner 内部读上游 stage）
                "stage_constraints": (state.get("stage_constraints") or {}).get(
                    node_name, {}
                ),
            }
            if requires_session_context:
                runner_kwargs["session_context"] = state.get("session_context")
            if resolve_retrieval_facade:
                retrieval_facade = deps.retrieval_facade
                if retrieval_facade is None:
                    retrieval_facade = deps.retrieval_facade_factory()
                runner_kwargs["retrieval_facade"] = retrieval_facade
            if requires_llm_client:
                runner_kwargs["llm_client"] = deps.llm_client
            if requires_external_context_retriever:
                runner_kwargs["external_context_retriever"] = deps.external_context_retriever
            if requires_target_analysis_service:
                runner_kwargs["target_analysis_service"] = deps.target_analysis_service
            if requires_structured_data_service:
                runner_kwargs["structured_data_service"] = deps.structured_data_service
            if requires_reporting_service:
                runner_kwargs["reporting_service"] = deps.reporting_service
            # verify_answer 节点：把已生成的答案文本喂给自检器
            if node_name == "verify_answer":
                fr = state.get("final_response")
                runner_kwargs["answer_text"] = getattr(fr, "summary", "") if fr else ""

            stage_result = runner(**runner_kwargs)
            new_observations = _append_observation(
                state,
                stage_result,
                input_summary={
                    "query": state["request"].query,
                    "intent": state["router_result"].intent,
                    "stage_constraints": runner_kwargs["stage_constraints"],
                },
            )
            update: dict[str, Any] = {
                node_name: stage_result,
                "stage_observations": new_observations,
            }
            # synthesize_answer 产出 final_response，提取到顶层
            final_response = stage_result.output_payload.get("final_response")
            if final_response is not None:
                update["final_response"] = final_response
            # verify_answer 节点：把自检结果挂回 final_response（若有）
            if node_name == "verify_answer":
                verification = stage_result.output_payload.get("verification")
                if verification is not None:
                    existing = state.get("final_response")
                    if existing is not None:
                        existing.verification = verification
                        update["final_response"] = existing
            _emit_stage_finished(emitter, node_name, started_at, stage_result)
            return update
        except Exception as exc:
            _emit_stage_finished(emitter, node_name, started_at)
            raise

    return node_fn


# 各 stage 节点通过工厂生成
query_structured_data_node = _make_stage_node(
    "query_structured_data",
    run_query_structured_data_stage,
    requires_structured_data_service=True,
)
collect_event_context_node = _make_stage_node(
    "collect_event_context",
    run_collect_event_context_stage,
    resolve_retrieval_facade=True,
    requires_external_context_retriever=True,
)
analyze_targets_node = _make_stage_node(
    "analyze_targets",
    run_analyze_targets_stage,
    requires_session_context=True,
    requires_external_context_retriever=True,
    requires_target_analysis_service=True,
)
retrieve_evidence_node = _make_stage_node(
    "retrieve_evidence",
    run_retrieve_evidence_stage,
    resolve_retrieval_facade=True,
    requires_llm_client=True,
)
synthesize_answer_node = _make_stage_node(
    "synthesize_answer",
    run_synthesize_answer_stage,
    requires_reporting_service=True,
)
reflect_and_requery_node = _make_stage_node(
    "reflect_and_requery",
    run_reflect_and_requery_stage,
    requires_structured_data_service=True,
    requires_llm_client=True,
)
verify_answer_node = _make_stage_node(
    "verify_answer",
    run_verify_answer_stage,
    requires_llm_client=True,
)


def build_trace_node(state: OrchestratorState) -> dict:
    """组装 trace_blocks 节点。

    把 routing + stage_planning + execution 三个 trace_block 组装到一起，
    替代旧 workbench_backend_api/service.py 的 _build_trace_blocks。
    """
    emitter = get_active_run_event_emitter()
    started_at = _emit_stage_started(emitter, "build_trace")
    try:
        request = state["request"]
        router_result = state["router_result"]
        stages = list(state.get("stages", []) or [])
        response_mode = state.get("response_mode", "")
        strategy_payload = state.get("strategy_payload")
        stage_observations = list(state.get("stage_observations", []) or [])
        final_response = state.get("final_response")
        guardrail_response = state.get("guardrail_response")

        trace_blocks: list[TraceBlock] = []
        if not request.include_trace:
            _emit_stage_finished(emitter, "build_trace", started_at)
            return {"trace_blocks": trace_blocks}

        # routing block
        trace_blocks.append(
            TraceBlock(
                block_type="routing",
                title="路由结果",
                status="success",
                payload_summary={
                    "intent": router_result.intent,
                    "follow_up_type": router_result.follow_up_type,
                    "query_mode": request.query_mode,
                },
                raw_refs=[router_result.intent],
            )
        )

        # stage_planning block
        stage_planning_summary: dict[str, Any] = {
            "intent": router_result.intent,
            "stage_count": len(stages),
            "stages": stages,
            "response_mode": response_mode,
        }
        if strategy_payload is not None:
            stage_planning_summary["strategy"] = strategy_payload.get("strategy", "")
            stage_planning_summary["strategy_confidence"] = strategy_payload.get(
                "confidence", ""
            )
        trace_blocks.append(
            TraceBlock(
                block_type="stage_planning",
                title="阶段计划结果",
                status="success",
                payload_summary=stage_planning_summary,
                raw_refs=stages,
            )
        )

        # execution block：复用 trace_builder，构造一个临时 OrchestrationResult
        orchestration_result = OrchestrationResult(
            session_id=request.session_id or "sess_stub",
            router_result=router_result,
            stages=stages,
            stage_constraints=state.get("stage_constraints", {}),
            response_mode=response_mode,
            stage_observations=stage_observations,
            final_response=final_response,
            guardrail_response=guardrail_response,
        )
        trace_blocks.append(build_execution_trace_block(orchestration_result))

        _emit_stage_finished(emitter, "build_trace", started_at)
        return {"trace_blocks": trace_blocks}
    except Exception as exc:
        _emit_stage_finished(emitter, "build_trace", started_at)
        raise


def save_snapshot_node(state: OrchestratorState) -> dict:
    """保存会话快照节点（副作用节点，无返回值）。"""
    deps = get_dependencies()
    emitter = get_active_run_event_emitter()
    started_at = _emit_stage_started(emitter, "save_snapshot")
    try:
        router_result = state["router_result"]
        if router_result.intent == Intent.OUT_OF_SCOPE.value:
            _emit_stage_finished(emitter, "save_snapshot", started_at)
            return {}

        final_response = state.get("final_response")
        guardrail_response = state.get("guardrail_response")
        if final_response is None and guardrail_response is None:
            _emit_stage_finished(emitter, "save_snapshot", started_at)
            return {}

        request = state["request"]
        stages = list(state.get("stages", []) or [])
        orchestration_result = OrchestrationResult(
            session_id=request.session_id or "sess_stub",
            router_result=router_result,
            stages=stages,
            stage_constraints=state.get("stage_constraints", {}),
            response_mode=state.get("response_mode", ""),
            stage_observations=list(state.get("stage_observations", []) or []),
            final_response=final_response,
            guardrail_response=guardrail_response,
        )
        snapshot = deps.session_service.build_snapshot(
            request=request,
            router_result=router_result,
            stages=stages,
            orchestration_result=orchestration_result,
        )
        if snapshot is not None:
            deps.session_service.save_snapshot(snapshot)
        _emit_stage_finished(emitter, "save_snapshot", started_at)
        return {}
    except Exception as exc:
        _emit_stage_finished(emitter, "save_snapshot", started_at)
        _logger.warning("save_snapshot 失败，不影响主流程: %s", exc)
        return {}


# ──────────────────────────────────────────────────────────────────
# 条件边函数
# ──────────────────────────────────────────────────────────────────


def _after_route(state: OrchestratorState) -> str:
    """route 节点后的条件边：按 intent 分流。

    - out_of_scope → guardrail 短路
    - 其余 intent → plan_stages（event 意图的策略分类已在 plan_stages 内部的
      build_plan 中完成，无需单独的 classify_strategy 节点）
    """
    intent = state["router_result"].intent
    if should_short_circuit(intent):
        return "guardrail"
    return "plan_stages"


def _after_plan(state: OrchestratorState) -> str:
    """plan_stages 节点后的条件边：按 stages 列表路由到第一个 stage 节点。

    stages 列表为空时（理论上不会发生，因为 out_of_scope 在 route 后短路），
    走 build_trace 兜底。
    """
    stages = state.get("stages", []) or []
    if not stages:
        return "build_trace"
    return stages[0]


def _after_stage(current_stage: str, state: OrchestratorState) -> str:
    """每个 stage 执行后的条件边：找 stages 列表里的下一个 stage。

    如果当前 stage 是最后一个，走 build_trace。
    """
    stages = state.get("stages", []) or []
    try:
        idx = stages.index(current_stage)
    except ValueError:
        return "build_trace"
    if idx + 1 >= len(stages):
        return "build_trace"
    return stages[idx + 1]


# ──────────────────────────────────────────────────────────────────
# 图构建
# ──────────────────────────────────────────────────────────────────


def build_graph(deps: NodeDependencies) -> Any:
    """构建并编译 LangGraph StateGraph。

    Args:
        deps: 节点依赖容器，包含所有 service 依赖

    Returns:
        编译后的 LangGraph runnable，支持 invoke / stream / astream

    LangSmith tracing 说明：
        若环境变量 LANGCHAIN_TRACING_V2=true 且 LANGCHAIN_API_KEY 已设置，
        graph.invoke() / graph.stream() 会自动上报每个节点的输入输出、
        执行时间、异常到 LangSmith UI（https://smith.langchain.com）。
        可在 UI 中查看完整的 State 流转、节点耗时、条件边决策。
    """
    configure_dependencies(deps)

    # 配置 LangSmith tracing（由环境变量驱动，未配置时静默跳过）
    if setup_langsmith_tracing():
        _logger.info(
            "LangSmith tracing 已启用，追踪数据将上报到 project=%s",
            __import__("os").getenv("LANGCHAIN_PROJECT", "finsight-agent"),
        )

    graph = StateGraph(OrchestratorState)

    # ── 添加所有节点 ──
    graph.add_node("load_session", load_session_node)
    graph.add_node("route", route_node)
    graph.add_node("plan_stages", plan_stages_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node(
        StageName.QUERY_STRUCTURED_DATA.value, query_structured_data_node
    )
    graph.add_node(
        StageName.COLLECT_EVENT_CONTEXT.value, collect_event_context_node
    )
    graph.add_node(StageName.ANALYZE_TARGETS.value, analyze_targets_node)
    graph.add_node(StageName.RETRIEVE_EVIDENCE.value, retrieve_evidence_node)
    graph.add_node(StageName.SYNTHESIZE_ANSWER.value, synthesize_answer_node)
    graph.add_node(StageName.REFLECT_AND_REQUERY.value, reflect_and_requery_node)
    graph.add_node(StageName.VERIFY_ANSWER.value, verify_answer_node)
    graph.add_node("build_trace", build_trace_node)
    graph.add_node("save_snapshot", save_snapshot_node)

    # ── 入口 ──
    graph.set_entry_point("load_session")

    # ── 线性边 ──
    graph.add_edge("load_session", "route")
    graph.add_edge("guardrail", "build_trace")
    graph.add_edge("build_trace", "save_snapshot")
    graph.add_edge("save_snapshot", END)

    # ── 条件边 ──
    graph.add_conditional_edges(
        "route",
        _after_route,
        {
            "guardrail": "guardrail",
            "plan_stages": "plan_stages",
        },
    )
    graph.add_conditional_edges("plan_stages", _after_plan)
    # 每个 stage 节点执行后，条件边找下一个 stage
    for stage_name in [
        StageName.QUERY_STRUCTURED_DATA.value,
        StageName.COLLECT_EVENT_CONTEXT.value,
        StageName.ANALYZE_TARGETS.value,
        StageName.RETRIEVE_EVIDENCE.value,
        StageName.SYNTHESIZE_ANSWER.value,
        StageName.REFLECT_AND_REQUERY.value,
        StageName.VERIFY_ANSWER.value,
    ]:
        graph.add_conditional_edges(
            stage_name,
            functools.partial(_after_stage, stage_name),
        )

    return graph.compile()
