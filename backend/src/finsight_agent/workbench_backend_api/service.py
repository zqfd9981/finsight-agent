from __future__ import annotations

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.trace_block import TraceBlock
from shared.enums.intent import Intent

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    StubRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
    TrainedRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.planner.service import PlannerService
from finsight_agent.control_plane.router.service import RouterService
from finsight_agent.control_plane.session.service import SessionService


class WorkbenchBackendApiService:
    """Unified route -> classify -> plan -> orchestrate entrypoint."""

    def __init__(
        self,
        *,
        router_service: RouterService | None = None,
        planner_service: PlannerService | None = None,
        orchestrator_service: OrchestratorService | None = None,
        session_service: SessionService | None = None,
        retrieval_strategy_classifier=None,
    ) -> None:
        self._router_service = router_service or RouterService()
        self._planner_service = planner_service or PlannerService()
        self._orchestrator_service = orchestrator_service or OrchestratorService()
        self._session_service = session_service or SessionService()
        self._retrieval_strategy_classifier = (
            retrieval_strategy_classifier
            or TrainedRetrievalStrategyClassifier(
                fallback=StubRetrievalStrategyClassifier(),
            )
        )

    def build_response(self, request: AnalysisRequest) -> AnalysisResponseEnvelope:
        session_id = request.session_id or self._build_session_id()
        session_context = self._session_service.load_context(request.session_id)
        router_result = self._router_service.route(
            query=request.query,
            session_context=session_context,
        )
        strategy_payload = self._classify_event_strategy(
            query=request.query,
            router_result=router_result,
            session_context=session_context,
        )
        plan = self._planner_service.build_plan(
            router_result,
            strategy_payload=strategy_payload,
        )
        normalized_request = AnalysisRequest(
            query=request.query,
            query_mode=request.query_mode,
            session_id=session_id,
            include_trace=request.include_trace,
            notes=request.notes,
        )
        orchestration_result = self._orchestrator_service.execute(
            request=normalized_request,
            router_result=router_result,
            plan=plan,
            session_context=session_context,
        )

        snapshot = self._session_service.build_snapshot(
            request=normalized_request,
            router_result=router_result,
            plan=plan,
            orchestration_result=orchestration_result,
        )
        if snapshot is not None:
            self._session_service.save_snapshot(snapshot)

        trace_blocks: list[TraceBlock] = []
        if request.include_trace:
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
            planning_summary = {
                "plan_id": plan.plan_id,
                "intent": plan.intent,
                "stage_count": len(plan.stages),
                "stages": list(plan.stages),
            }
            if strategy_payload is not None:
                planning_summary["strategy"] = strategy_payload.get("strategy", "")
                planning_summary["strategy_confidence"] = strategy_payload.get(
                    "confidence", ""
                )
            trace_blocks.append(
                TraceBlock(
                    block_type="planning",
                    title="计划结果",
                    status="success",
                    payload_summary=planning_summary,
                    raw_refs=list(plan.stages),
                )
            )
            trace_blocks.extend(orchestration_result.trace_blocks)

        response = orchestration_result.final_response or orchestration_result.guardrail_response
        return AnalysisResponseEnvelope(
            session_id=session_id,
            turn_id="turn_stub",
            response=response,
            trace_blocks=trace_blocks,
        )

    def _build_session_id(self) -> str:
        import uuid

        return f"sess_{uuid.uuid4().hex[:8]}"

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
