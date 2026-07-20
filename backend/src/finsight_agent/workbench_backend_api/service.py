from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from queue import Queue
from threading import Thread
from typing import Any

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.enums.intent import Intent

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    StubRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.orchestrator.llm_strategy_classifier import (
    LlmRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
    TrainedRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.evidence_index_builder import (
    build_evidence_index,
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
            or LlmRetrievalStrategyClassifier(
                llm_client=self._llm_client,
                fallback=TrainedRetrievalStrategyClassifier(
                    fallback=StubRetrievalStrategyClassifier(),
                ),
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
        current_stage_name = ""
        current_stage_started_at: str | None = None
        session_id = request.session_id or self._build_session_id()

        try:
            with bind_active_run_event_emitter(emitter):
                # ── LangGraph 编排路径（唯一路径）──
                # 全流程委托给 OrchestratorService.execute_graph，router/classify/plan/
                # stage 执行/trace/snapshot 都在图内完成（run_started 由 execute_graph 内部发射）。
                # session_context 由图内 load_session 节点加载，这里不再预先 load（去重）。
                normalized_request = AnalysisRequest(
                    query=request.query,
                    query_mode=request.query_mode,
                    session_id=session_id,
                    include_trace=request.include_trace,
                    notes=request.notes,
                )
                orchestration_result = self._orchestrator_service.execute_graph(
                    request=normalized_request,
                    session_context=None,
                    event_callback=event_callback,
                    router_service=self._router_service,
                    session_service=self._session_service,
                    strategy_classifier=self._retrieval_strategy_classifier,
                )
                envelope = AnalysisResponseEnvelope(
                    session_id=session_id,
                    turn_id="turn_stub",
                    response=(
                        orchestration_result.final_response
                        or orchestration_result.guardrail_response
                    ),
                    trace_blocks=orchestration_result.trace_blocks,
                    evidence_index=build_evidence_index(orchestration_result),
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
