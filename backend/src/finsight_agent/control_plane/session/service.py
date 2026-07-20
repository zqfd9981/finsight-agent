from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from finsight_agent.control_plane.orchestrator.models import OrchestrationResult
from finsight_agent.infra.llm import LlmClient
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from .extractor import SessionContextExtractor
from .models import SessionSnapshot
from .repository import SessionRepository
from .summarizer import summarize_history

_logger = logging.getLogger(__name__)

# 短期记忆保留的最大轮次（超过则压缩最早的进 history_summary）
_MAX_TURNS = 3


class SessionService:
    """统一入口可消费的 session service（v2 支持多轮记忆）。"""

    def __init__(
        self,
        *,
        repository: SessionRepository | None = None,
        extractor: SessionContextExtractor | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._repository = repository or SessionRepository()
        self._extractor = extractor or SessionContextExtractor()
        self._llm_client = llm_client

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

        # 当 turns 超过 _MAX_TURNS 时，压缩最早轮次到 history_summary
        # extractor 已截断到 _MAX_TURNS，这里检查是否需要压缩
        # 注：extractor 内部已做 new_turns[-_MAX_TURNS:]，所以这里
        # 通过对比 previous_turns 长度判断是否有轮次被截掉
        context = self._maybe_compress_history(
            context=context,
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

    def _maybe_compress_history(
        self,
        *,
        context: SessionContext,
        previous_context: SessionContext | None,
    ) -> SessionContext:
        """当有轮次被截掉时，用 LLM 压缩成 history_summary。

        extractor 内部已做 turns[-3:] 截断，所以当 previous_turns >= 3 时，
        最早的 1 轮会被截掉，这里把它压缩进 history_summary。
        """
        if previous_context is None:
            return context

        previous_turns = list(previous_context.turns)
        if len(previous_turns) < _MAX_TURNS:
            # 上一轮还没满 3 轮，本轮 append 后不会截断，无需压缩
            return context

        # 上一轮已有 3 轮，本轮 append 后会被截断 1 轮
        # 找出被截掉的那一轮（previous_turns[0]）
        dropped_turn = previous_turns[0]
        existing_summary = previous_context.history_summary or ""

        try:
            new_summary = summarize_history(
                llm_client=self._llm_client,
                existing_summary=existing_summary,
                turns_to_compress=[dropped_turn],
            )
            context.history_summary = new_summary
        except Exception as exc:
            _logger.warning("历史摘要压缩失败，保留旧摘要: %s", exc)

        return context
