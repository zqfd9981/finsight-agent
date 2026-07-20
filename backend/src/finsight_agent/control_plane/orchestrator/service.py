from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.service import (
    RetrievalFacade,
    build_retrieval_facade,
    get_shared_retrieval_facade,
)
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.control_plane.router.service import RouterService
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.infra.llm.client import LlmClient
from finsight_agent.shared.utils.execution_events import (
    EventCallback,
    RunEventEmitter,
    bind_active_run_event_emitter,
    get_active_run_event_emitter,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from finsight_agent.infra.external.bocha_event_search import BochaEventSearchProvider
from finsight_agent.infra.external.official_disclosure_search import (
    OfficialDisclosureSearchProvider,
)
from .context_retriever import ExternalContextRetriever
from .context_retrieval_planner import ContextRetrievalPlanner
from .dual_source_context_retriever import DualSourceExternalContextRetriever
from .models import OrchestrationResult
from .node_deps import NodeDependencies
from .observation_builder import build_stage_observation
from .policies import build_guardrail_response, should_short_circuit
from .stage_runners import STAGE_RUNNERS
from .target_analysis import TargetAnalysisService
from .trace_builder import build_execution_trace_block

_logger = logging.getLogger(__name__)


class OrchestratorService:
    """Stage orchestrator."""

    def __init__(
        self,
        *,
        structured_data_service: StructuredDataService | None = None,
        reporting_service: ReportingService | None = None,
        retrieval_facade: RetrievalFacade | None = None,
        retrieval_facade_factory: Callable[[], RetrievalFacade] | None = None,
        external_context_retriever: ExternalContextRetriever | None = None,
        target_analysis_service: TargetAnalysisService | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        if structured_data_service is not None:
            self._structured_data_service = structured_data_service
        else:
            from finsight_agent.config.settings import load_settings

            sd_settings = load_settings().structured_data
            normalizer = MetricNormalizer(aliases_path=sd_settings.aliases_path)
            self._structured_data_service = StructuredDataService(normalizer=normalizer)
        self._reporting_service = reporting_service or ReportingService()
        self._retrieval_facade = retrieval_facade
        # 默认指向进程级缓存单例（get_shared_retrieval_facade），确保 dense 检索
        # facade（及 bge-m3 模型）只构建一次，避免每次请求都重新加载模型并触发
        # torch/OpenMP 初始化竞态导致的偶发 SIGSEGV（详见 bge_m3.py 注释）。
        self._retrieval_facade_factory = (
            retrieval_facade_factory or get_shared_retrieval_facade
        )
        self._external_context_retriever = (
            external_context_retriever or _build_default_external_context_retriever()
        )
        self._target_analysis_service = target_analysis_service or TargetAnalysisService()
        self._llm_client = llm_client

    def _resolve_event_emitter(
        self,
        *,
        event_callback: EventCallback | None,
    ) -> tuple[RunEventEmitter | None, bool]:
        active = get_active_run_event_emitter()
        if active is not None:
            return active, False
        if event_callback is None:
            return None, False
        return RunEventEmitter(run_id="run_stub", event_callback=event_callback), True

    def _resolve_retrieval_facade(
        self,
        *,
        cached_facade: RetrievalFacade | None = None,
    ) -> tuple[RetrievalFacade, bool]:
        if cached_facade is not None:
            return cached_facade, False
        if self._retrieval_facade is not None:
            return self._retrieval_facade, False
        retrieval_facade = self._retrieval_facade_factory()
        return retrieval_facade, True

    # ──────────────────────────────────────────────────────────────
    # LangGraph 编排实现（单一入口，取代旧 execute）
    # ──────────────────────────────────────────────────────────────

    def execute_graph(
        self,
        *,
        request: AnalysisRequest,
        session_context: SessionContext | None,
        event_callback: EventCallback | None = None,
        router_service: RouterService | None = None,
        session_service: SessionService | None = None,
        strategy_classifier: object | None = None,
    ) -> OrchestrationResult:
        """LangGraph 编排入口：构建图并执行全流程。

        与旧 execute 的区别：
        - 自己负责 router → classify → plan → stage 执行 → trace → snapshot 全流程
        - State 在节点间显式流转，无 execution_state mutable dict
        - stage 链由条件边动态串联（为 Step B ReAct 反思铺路）

        Args:
            request: 分析请求
            session_context: 会话上下文（已由上层加载，传给 load_session 节点）
            event_callback: SSE 事件回调
            router_service: 路由服务（None 时用默认）
            session_service: 会话服务（None 时用默认）
            strategy_classifier: 策略分类器（None 时用默认）

        Returns:
            OrchestrationResult，包含 final_response / guardrail_response / trace_blocks
        """
        # 延迟导入 graph 模块，避免在模块加载时触发 langgraph 依赖
        from .graph import build_graph

        emitter, owns_binding = self._resolve_event_emitter(event_callback=event_callback)

        # 构建 NodeDependencies
        deps = NodeDependencies(
            router_service=router_service or RouterService(llm_client=self._llm_client),
            structured_data_service=self._structured_data_service,
            reporting_service=self._reporting_service,
            retrieval_facade_factory=self._retrieval_facade_factory,
            external_context_retriever=self._external_context_retriever,
            target_analysis_service=self._target_analysis_service,
            session_service=session_service or SessionService(llm_client=self._llm_client),
            strategy_classifier=strategy_classifier
            or _build_default_strategy_classifier(llm_client=self._llm_client),
            llm_client=self._llm_client,
            retrieval_facade=self._retrieval_facade,
        )

        graph = build_graph(deps)

        initial_state = {
            "request": request,
            "session_context": session_context,
            "stage_observations": [],
        }

        # LangSmith trace metadata：在 UI 中按 query/session_id/intent 筛选 trace
        run_metadata = {
            "query": request.query,
            "session_id": request.session_id or "",
            "query_mode": request.query_mode,
        }

        def _run() -> OrchestrationResult:
            try:
                if emitter is not None:
                    emitter.emit_run_started()
                final_state = graph.invoke(
                    initial_state,
                    config={"metadata": run_metadata},
                )
            except Exception as exc:
                if emitter is not None:
                    emitter.emit_error(
                        stage_name="",
                        message=f"graph execution failed: {exc}",
                        started_at=None,
                    )
                raise

            # 从 final_state 组装 OrchestrationResult（保持与旧 execute 的返回结构一致）
            request_id = request.session_id or "sess_stub"
            result = OrchestrationResult(
                session_id=request_id,
                router_result=final_state.get("router_result"),
                stages=list(final_state.get("stages", []) or []),
                stage_constraints=final_state.get("stage_constraints", {}) or {},
                response_mode=final_state.get("response_mode", "") or "",
                stage_observations=list(final_state.get("stage_observations", []) or []),
                final_response=final_state.get("final_response"),
                guardrail_response=final_state.get("guardrail_response"),
            )
            result.trace_blocks = list(final_state.get("trace_blocks", []) or [])
            return result

        if owns_binding:
            with bind_active_run_event_emitter(emitter):
                return _run()
        return _run()


def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
    return DualSourceExternalContextRetriever(
        planner=ContextRetrievalPlanner(),
        event_search_provider=BochaEventSearchProvider(),
        disclosure_search_provider=OfficialDisclosureSearchProvider(),
    )


def _build_default_strategy_classifier(llm_client=None):
    """构建默认的 retrieval strategy classifier（带 stub fallback）。

    默认主路径为 LLM 判断（LlmRetrievalStrategyClassifier），失败时回退到
    Trained 分类器 + Stub。可用 FINSIGHT_LLM_STRATEGY_ENABLED=0 关闭 LLM 主路径。
    """
    from ..config.feature_flags import llm_strategy_enabled
    from .llm_strategy_classifier import LlmRetrievalStrategyClassifier
    from .retrieval_strategy_classifier import StubRetrievalStrategyClassifier
    from .trained_strategy_classifier import TrainedRetrievalStrategyClassifier

    trained = TrainedRetrievalStrategyClassifier(
        fallback=StubRetrievalStrategyClassifier(),
    )
    if llm_client is not None and llm_strategy_enabled():
        return LlmRetrievalStrategyClassifier(
            llm_client=llm_client,
            fallback=trained,
        )
    return trained


def _build_stage_message(stage_result) -> str:
    if stage_result.degraded_reason:
        return stage_result.degraded_reason
    if stage_result.user_summary:
        return stage_result.user_summary
    return f"{stage_result.stage_name} finished"


def _build_stage_payload(stage_result) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_ref_count": len(stage_result.evidence_refs),
    }
    if stage_result.degraded_reason:
        payload["degraded_reason"] = stage_result.degraded_reason
    if "final_response" in stage_result.output_payload:
        payload["has_final_response"] = True
    return payload
