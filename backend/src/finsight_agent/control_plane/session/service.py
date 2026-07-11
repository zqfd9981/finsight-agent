from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from finsight_agent.control_plane.orchestrator.models import OrchestrationResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from .extractor import SessionContextExtractor
from .models import SessionSnapshot
from .repository import SessionRepository


class SessionService:
    """统一入口可消费的首版 session service。"""

    def __init__(
        self,
        *,
        repository: SessionRepository | None = None,
        extractor: SessionContextExtractor | None = None,
    ) -> None:
        self._repository = repository or SessionRepository()
        self._extractor = extractor or SessionContextExtractor()

    def load_context(self, session_id: str | None) -> SessionContext | None:
        if not session_id:
            return None
        snapshot = self._repository.load(session_id)
        if snapshot is None:
            return None
        return snapshot.context

    def build_snapshot(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        stages: list[str],
        orchestration_result: OrchestrationResult,
    ) -> SessionSnapshot | None:
        if router_result.intent == "out_of_scope":
            return None

        if (
            orchestration_result.final_response is None
            and orchestration_result.guardrail_response is None
        ):
            return None

        previous_context = None
        if request.session_id:
            existing_snapshot = self._repository.load(request.session_id)
            if existing_snapshot is not None:
                previous_context = existing_snapshot.context

        context = self._extractor.extract(
            request=request,
            router_result=router_result,
            orchestration_result=orchestration_result,
            previous_context=previous_context,
        )

        return SessionSnapshot(
            session_id=orchestration_result.session_id,
            last_query=request.query,
            last_query_mode=request.query_mode,
            last_intent=router_result.intent,
            last_follow_up_type=router_result.follow_up_type,
            last_plan_stages=list(stages),
            context=context,
            updated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        )

    def save_snapshot(self, snapshot: SessionSnapshot) -> None:
        self._repository.save(snapshot)
