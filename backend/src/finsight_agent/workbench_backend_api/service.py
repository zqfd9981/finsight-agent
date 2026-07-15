from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from queue import Queue
from threading import Thread
from typing import Any

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.trace_block import TraceBlock
from shared.enums.intent import Intent

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    StubRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.orchestrator.stage_planner import resolve_stages
from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
    TrainedRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.router.service import RouterService
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.infra.llm.client import LlmClient
from finsight_agent.shared.utils.execution_events import (
    EventCallback,
    RunEventEmitter,
    bind_active_run_event_emitter,
)


class WorkbenchBackendApiService:
    """Unified route -> classify -> stage-plan -> orchestrate entrypoint."""

    def __init__(
        self,
        *,
        router_service: RouterService | None = None,
        orchestrator_service: OrchestratorService | None = None,
        session_service: SessionService | None = None,
        retrieval_strategy_classifier=None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._router_service = router_service or RouterService()
        self._llm_client = llm_client or LlmClient()
        if orchestrator_service is not None:
            self._orchestrator_service = orchestrator_service
        else:
            self._orchestrator_service = OrchestratorService(
                llm_client=self._llm_client,
            )
        self._session_service = session_service or SessionService()
        self._retrieval_strategy_classifier = (
            retrieval_strategy_classifier
            or TrainedRetrievalStrategyClassifier(
                fallback=StubRetrievalStrategyClassifier(),
            )
        )

    def build_response(self, request: AnalysisRequest) -> AnalysisResponseEnvelope:
        return self._execute_request(request=request)

    def stream_response_events(self, request: AnalysisRequest) -> Iterator:
        run_id = self._build_run_id()
        queue: Queue[object] = Queue()
        sentinel = object()

        def _worker() -> None:
            try:
                self._execute_request(
                    request=request,
                    event_callback=queue.put,
                    run_id=run_id,
                    raise_on_error=False,
                )
            finally:
                queue.put(sentinel)

        Thread(target=_worker, daemon=True).start()

        while True:
            item = queue.get()
            if item is sentinel:
                return
            yield item

    def _execute_request(
        self,
        *,
        request: AnalysisRequest,
        event_callback: EventCallback | None = None,
        run_id: str | None = None,
        raise_on_error: bool = True,
    ) -> AnalysisResponseEnvelope:
        emitter = self._build_event_emitter(
            event_callback=event_callback,
            run_id=run_id,
        )
        if emitter is not None:
            emitter.emit_run_started()

        current_stage_name = ""
        current_stage_started_at: str | None = None
        session_id = request.session_id or self._build_session_id()

        try:
            with bind_active_run_event_emitter(emitter):
                session_context = self._session_service.load_context(request.session_id)

                current_stage_name = "routing"
                current_stage_started_at = self._emit_stage_started(
                    emitter=emitter,
                    stage_name=current_stage_name,
                    message="Routing started",
                )
                router_result = self._router_service.route(
                    query=request.query,
                    session_context=session_context,
                )
                self._emit_stage_finished(
                    emitter=emitter,
                    stage_name=current_stage_name,
                    started_at=current_stage_started_at,
                    status="success",
                    message="Routing finished",
                    payload={
                        "intent": router_result.intent,
                        "follow_up_type": router_result.follow_up_type,
                        "confidence": router_result.confidence,
                    },
                )

                current_stage_name = "stage_planning"
                current_stage_started_at = self._emit_stage_started(
                    emitter=emitter,
                    stage_name=current_stage_name,
                    message="Stage planning started",
                )
                strategy_payload = self._classify_event_strategy(
                    query=request.query,
                    router_result=router_result,
                    session_context=session_context,
                )
                stages, stage_constraints, response_mode = resolve_stages(
                    router_result,
                    strategy_payload=strategy_payload,
                )
                self._emit_stage_finished(
                    emitter=emitter,
                    stage_name=current_stage_name,
                    started_at=current_stage_started_at,
                    status="success",
                    message="Stage planning finished",
                    payload={
                        "intent": router_result.intent,
                        "stages": list(stages),
                        "response_mode": response_mode,
                        "strategy": (
                            strategy_payload.get("strategy", "")
                            if strategy_payload is not None
                            else ""
                        ),
                    },
                )

                normalized_request = AnalysisRequest(
                    query=request.query,
                    query_mode=request.query_mode,
                    session_id=session_id,
                    include_trace=request.include_trace,
                    notes=request.notes,
                )
                current_stage_name = "execution"
                current_stage_started_at = None
                orchestration_result = self._orchestrator_service.execute(
                    request=normalized_request,
                    router_result=router_result,
                    stages=stages,
                    stage_constraints=stage_constraints,
                    response_mode=response_mode,
                    session_context=session_context,
                    event_callback=event_callback,
                )

                snapshot = self._session_service.build_snapshot(
                    request=normalized_request,
                    router_result=router_result,
                    stages=stages,
                    orchestration_result=orchestration_result,
                )
                if snapshot is not None:
                    self._session_service.save_snapshot(snapshot)

                envelope = AnalysisResponseEnvelope(
                    session_id=session_id,
                    turn_id="turn_stub",
                    response=(
                        orchestration_result.final_response
                        or orchestration_result.guardrail_response
                    ),
                    trace_blocks=self._build_trace_blocks(
                        request=request,
                        router_result=router_result,
                        stages=stages,
                        response_mode=response_mode,
                        orchestration_result=orchestration_result,
                        strategy_payload=strategy_payload,
                    ),
                )
                if emitter is not None:
                    emitter.emit_run_finished(
                        message="Final response ready",
                        final_response=asdict(envelope.response),
                        payload={"response_envelope": asdict(envelope)},
                    )
                return envelope
        except Exception as exc:  # noqa: BLE001
            if emitter is not None:
                emitter.emit_error(
                    stage_name="" if current_stage_name == "execution" else current_stage_name,
                    message=f"{current_stage_name or 'analysis'} failed: {exc}",
                    started_at=current_stage_started_at,
                )
            if raise_on_error:
                raise
            return AnalysisResponseEnvelope(session_id=session_id)

    def _build_trace_blocks(
        self,
        *,
        request: AnalysisRequest,
        router_result,
        stages: list[str],
        response_mode: str,
        orchestration_result,
        strategy_payload: dict[str, str] | None,
    ) -> list[TraceBlock]:
        trace_blocks: list[TraceBlock] = []
        if not request.include_trace:
            return trace_blocks

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
        stage_planning_summary = {
            "intent": router_result.intent,
            "stage_count": len(stages),
            "stages": list(stages),
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
                raw_refs=list(stages),
            )
        )
        trace_blocks.extend(orchestration_result.trace_blocks)
        return trace_blocks

    def _build_event_emitter(
        self,
        *,
        event_callback: EventCallback | None,
        run_id: str | None,
    ) -> RunEventEmitter | None:
        if event_callback is None:
            return None
        return RunEventEmitter(
            run_id=run_id or self._build_run_id(),
            event_callback=event_callback,
        )

    def _emit_stage_started(
        self,
        *,
        emitter: RunEventEmitter | None,
        stage_name: str,
        message: str,
    ) -> str | None:
        if emitter is None:
            return None
        return emitter.emit_stage_started(stage_name=stage_name, message=message)

    def _emit_stage_finished(
        self,
        *,
        emitter: RunEventEmitter | None,
        stage_name: str,
        started_at: str | None,
        status: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if emitter is None:
            return
        emitter.emit_stage_finished(
            stage_name=stage_name,
            status=status,
            message=message,
            started_at=started_at,
            payload=payload,
        )

    def _build_session_id(self) -> str:
        import uuid

        return f"sess_{uuid.uuid4().hex[:8]}"

    def _build_run_id(self) -> str:
        import uuid

        return f"run_{uuid.uuid4().hex[:8]}"

    def _classify_event_strategy(
        self,
        *,
        query: str,
        router_result,
        session_context,
    ) -> dict[str, str] | None:
        if router_result.intent != Intent.EVENT_IMPACT_ANALYSIS.value:
            return None

        session_topic = ""
        if session_context is not None:
            session_topic = str(session_context.active_topic or "").strip()

        payload = self._retrieval_strategy_classifier.classify(
            query=query,
            router_payload={
                "intent": router_result.intent,
                "follow_up_type": router_result.follow_up_type,
                "confidence": router_result.confidence,
                "entities": router_result.entities,
                "needs": router_result.needs,
                "constraints": router_result.constraints,
            },
            session_topic=session_topic,
        )
        return {
            "strategy": str(payload.get("strategy") or "").strip(),
            "confidence": str(payload.get("confidence") or "").strip(),
            "reason": str(payload.get("reason") or "").strip(),
        }
