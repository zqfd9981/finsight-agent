from __future__ import annotations

from .analyze_targets import run_analyze_targets_stage
from .collect_event_context import run_collect_event_context_stage
from .query_structured_data import run_query_structured_data_stage
from .reflect_and_requery import run_reflect_and_requery_stage
from .retrieve_evidence import run_retrieve_evidence_stage
from .synthesize_answer import run_synthesize_answer_stage
from .verify_answer import run_verify_answer_stage


STAGE_RUNNERS = {
    "collect_event_context": run_collect_event_context_stage,
    "analyze_targets": run_analyze_targets_stage,
    "query_structured_data": run_query_structured_data_stage,
    "reflect_and_requery": run_reflect_and_requery_stage,
    "retrieve_evidence": run_retrieve_evidence_stage,
    "synthesize_answer": run_synthesize_answer_stage,
    "verify_answer": run_verify_answer_stage,
}


__all__ = [
    "STAGE_RUNNERS",
    "run_collect_event_context_stage",
    "run_analyze_targets_stage",
    "run_query_structured_data_stage",
    "run_reflect_and_requery_stage",
    "run_retrieve_evidence_stage",
    "run_synthesize_answer_stage",
    "run_verify_answer_stage",
]
