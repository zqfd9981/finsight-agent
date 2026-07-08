from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from shared.contracts.analysis_stream_event import AnalysisStreamEvent


EventCallback = Callable[[AnalysisStreamEvent], None]

_ACTIVE_RUN_EVENT_EMITTER: ContextVar["RunEventEmitter | None"] = ContextVar(
    "active_run_event_emitter",
    default=None,
)


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    if not started_at or not finished_at:
        return None
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    return max(0, int((finished - started).total_seconds() * 1000))


class RunEventEmitter:
    def __init__(self, *, run_id: str, event_callback: EventCallback) -> None:
        self.run_id = run_id
        self._event_callback = event_callback
        self._run_started_at: str | None = None

    @property
    def run_started_at(self) -> str | None:
        return self._run_started_at

    def emit(
        self,
        *,
        event_type: str,
        status: str,
        message: str,
        stage_name: str = "",
        started_at: str | None = None,
        finished_at: str | None = None,
        payload: dict[str, Any] | None = None,
        final_response: dict[str, Any] | None = None,
    ) -> AnalysisStreamEvent:
        event = AnalysisStreamEvent(
            event_type=event_type,
            run_id=self.run_id,
            stage_name=stage_name,
            status=status,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            payload=payload or {},
            final_response=final_response,
        )
        self._event_callback(event)
        return event

    def emit_run_started(self, *, message: str = "Analysis started") -> AnalysisStreamEvent:
        self._run_started_at = utc_now_iso()
        return self.emit(
            event_type="run_started",
            status="running",
            message=message,
            started_at=self._run_started_at,
        )

    def emit_stage_started(
        self,
        *,
        stage_name: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        started_at = utc_now_iso()
        self.emit(
            event_type="stage_started",
            stage_name=stage_name,
            status="running",
            message=message,
            started_at=started_at,
            payload=payload,
        )
        return started_at

    def emit_stage_finished(
        self,
        *,
        stage_name: str,
        status: str,
        message: str,
        started_at: str | None,
        payload: dict[str, Any] | None = None,
    ) -> AnalysisStreamEvent:
        finished_at = utc_now_iso()
        return self.emit(
            event_type="stage_finished",
            stage_name=stage_name,
            status=status,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            payload=payload,
        )

    def emit_run_finished(
        self,
        *,
        message: str,
        payload: dict[str, Any] | None = None,
        final_response: dict[str, Any] | None = None,
    ) -> AnalysisStreamEvent:
        finished_at = utc_now_iso()
        return self.emit(
            event_type="run_finished",
            status="success",
            message=message,
            started_at=self._run_started_at,
            finished_at=finished_at,
            payload=payload,
            final_response=final_response,
        )

    def emit_error(
        self,
        *,
        message: str,
        stage_name: str = "",
        started_at: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AnalysisStreamEvent:
        finished_at = utc_now_iso()
        return self.emit(
            event_type="error",
            stage_name=stage_name,
            status="failed",
            message=message,
            started_at=started_at or self._run_started_at,
            finished_at=finished_at,
            payload=payload,
        )


def get_active_run_event_emitter() -> RunEventEmitter | None:
    return _ACTIVE_RUN_EVENT_EMITTER.get()


@contextmanager
def bind_active_run_event_emitter(
    emitter: RunEventEmitter | None,
) -> Iterator[RunEventEmitter | None]:
    token = _ACTIVE_RUN_EVENT_EMITTER.set(emitter)
    try:
        yield emitter
    finally:
        _ACTIVE_RUN_EVENT_EMITTER.reset(token)


@contextmanager
def emit_nested_stage(
    *,
    stage_name: str,
    start_message: str,
    finish_message: str,
    payload: dict[str, Any] | None = None,
) -> Iterator[None]:
    emitter = get_active_run_event_emitter()
    if emitter is None:
        yield
        return

    started_at = emitter.emit_stage_started(
        stage_name=stage_name,
        message=start_message,
        payload=payload,
    )
    try:
        yield
    except Exception as exc:
        emitter.emit_error(
            stage_name=stage_name,
            message=f"{stage_name} failed: {exc}",
            started_at=started_at,
        )
        raise
    emitter.emit_stage_finished(
        stage_name=stage_name,
        status="success",
        message=finish_message,
        started_at=started_at,
        payload=payload,
    )
