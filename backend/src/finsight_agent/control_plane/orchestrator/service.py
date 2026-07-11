from __future__ import annotations

import uuid
from collections.abc import Callable

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.service import (
    RetrievalFacade,
    build_retrieval_facade,
)
from finsight_agent.capabilities.structured_data.service import StructuredDataService
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
from .observation_builder import build_stage_observation
from .policies import build_guardrail_response, should_short_circuit
from .stage_runners import STAGE_RUNNERS
from .target_analysis import TargetAnalysisService
from .trace_builder import build_execution_trace_block


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
    ) -> None:
        self._structured_data_service = structured_data_service or StructuredDataService()
        self._reporting_service = reporting_service or ReportingService()
        self._retrieval_facade = retrieval_facade
        self._retrieval_facade_factory = retrieval_facade_factory or build_retrieval_facade
        self._external_context_retriever = (
            external_context_retriever or _build_default_external_context_retriever()
        )
        self._target_analysis_service = target_analysis_service or TargetAnalysisService()

    def execute(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        stages: list[str],
        stage_constraints: dict[str, dict[str, object]],
        response_mode: str = "",
        session_context: SessionContext | None,
        event_callback: EventCallback | None = None,
    ) -> OrchestrationResult:
        result = OrchestrationResult(
            session_id=request.session_id or "sess_stub",
            router_result=router_result,
            stages=list(stages),
            stage_constraints=stage_constraints,
            response_mode=response_mode,
        )

        emitter, owns_binding = self._resolve_event_emitter(event_callback=event_callback)

        if should_short_circuit(router_result.intent):
            result.guardrail_response = build_guardrail_response(
                reason_code=router_result.constraints.get(
                    "reason_code",
                    "out_of_scope_request",
                ),
                progress_state="routing",
                partial_answer="当前请求超出 V1 支持范围，未进入常规执行流程。",
            )
            result.trace_blocks.append(build_execution_trace_block(result))
            return result

        execution_state: dict[str, object] = {}
        owned_retrieval_facade: RetrievalFacade | None = None

        def _run() -> OrchestrationResult:
            nonlocal owned_retrieval_facade
            try:
                for stage_name in stages:
                    runner = STAGE_RUNNERS[stage_name]
                    stage_constraints_for_stage = stage_constraints.get(stage_name, {})
                    runner_kwargs = {
                        "request": request,
                        "router_result": router_result,
                        "execution_state": execution_state,
                        "stage_constraints": stage_constraints_for_stage,
                    }
                    if stage_name == "query_structured_data":
                        runner_kwargs["structured_data_service"] = self._structured_data_service
                    elif stage_name == "collect_event_context":
                        retrieval_facade, is_owned = self._resolve_retrieval_facade(
                            cached_facade=owned_retrieval_facade
                        )
                        if is_owned and owned_retrieval_facade is None:
                            owned_retrieval_facade = retrieval_facade
                        runner_kwargs["retrieval_facade"] = retrieval_facade
                        runner_kwargs[
                            "external_context_retriever"
                        ] = self._external_context_retriever
                    elif stage_name == "analyze_targets":
                        runner_kwargs["session_context"] = session_context
                        runner_kwargs[
                            "external_context_retriever"
                        ] = self._external_context_retriever
                        runner_kwargs[
                            "target_analysis_service"
                        ] = self._target_analysis_service
                    elif stage_name == "synthesize_answer":
                        runner_kwargs["reporting_service"] = self._reporting_service
                    elif stage_name == "retrieve_evidence":
                        retrieval_facade, is_owned = self._resolve_retrieval_facade(
                            cached_facade=owned_retrieval_facade
                        )
                        if is_owned and owned_retrieval_facade is None:
                            owned_retrieval_facade = retrieval_facade
                        runner_kwargs["retrieval_facade"] = retrieval_facade

                    stage_started_at = None
                    if emitter is not None:
                        stage_started_at = emitter.emit_stage_started(
                            stage_name=stage_name,
                            message=f"{stage_name} started",
                        )
                    try:
                        stage_result = runner(**runner_kwargs)
                    except Exception as exc:
                        if emitter is not None:
                            emitter.emit_error(
                                stage_name=stage_name,
                                message=f"{stage_name} failed: {exc}",
                                started_at=stage_started_at,
                            )
                        raise

                    execution_state[stage_name] = stage_result
                    result.stage_observations.append(
                        build_stage_observation(
                            observation_id=f"obs_{uuid.uuid4().hex[:8]}",
                            input_summary={
                                "query": request.query,
                                "intent": router_result.intent,
                                "stage_constraints": stage_constraints_for_stage,
                            },
                            stage_result=stage_result,
                        )
                    )

                    if emitter is not None:
                        emitter.emit_stage_finished(
                            stage_name=stage_name,
                            status=str(stage_result.status or "success"),
                            message=_build_stage_message(stage_result),
                            started_at=stage_started_at,
                            payload=_build_stage_payload(stage_result),
                        )

                    final_response = stage_result.output_payload.get("final_response")
                    if final_response is not None:
                        result.final_response = final_response
            finally:
                if owned_retrieval_facade is not None:
                    owned_retrieval_facade.close()

            result.trace_blocks.append(build_execution_trace_block(result))
            return result

        if owns_binding:
            with bind_active_run_event_emitter(emitter):
                return _run()
        return _run()

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


def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
    return DualSourceExternalContextRetriever(
        planner=ContextRetrievalPlanner(),
        event_search_provider=BochaEventSearchProvider(),
        disclosure_search_provider=OfficialDisclosureSearchProvider(),
    )


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
