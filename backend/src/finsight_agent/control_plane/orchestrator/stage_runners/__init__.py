from __future__ import annotations

from .analyze_targets import run_analyze_targets_stage
from .collect_event_context import run_collect_event_context_stage
from .query_structured_data import run_query_structured_data_stage
from .retrieve_evidence import run_retrieve_evidence_stage
from .synthesize_brief_answer import run_synthesize_brief_answer_stage
from .synthesize_event_answer import run_synthesize_event_answer_stage
from .synthesize_report import run_synthesize_report_stage


STAGE_RUNNERS = {
    "collect_event_context": run_collect_event_context_stage,
    "analyze_targets": run_analyze_targets_stage,
    "query_structured_data": run_query_structured_data_stage,
    "synthesize_brief_answer": run_synthesize_brief_answer_stage,
    "synthesize_event_answer": run_synthesize_event_answer_stage,
    "retrieve_evidence": run_retrieve_evidence_stage,
    "synthesize_report": run_synthesize_report_stage,
}


__all__ = [
    "STAGE_RUNNERS",
    "run_collect_event_context_stage",
    "run_analyze_targets_stage",
    "run_query_structured_data_stage",
    "run_synthesize_brief_answer_stage",
    "run_synthesize_event_answer_stage",
    "run_retrieve_evidence_stage",
    "run_synthesize_report_stage",
]
