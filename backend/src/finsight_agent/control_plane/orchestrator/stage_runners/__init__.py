from __future__ import annotations

from .query_structured_data import run_query_structured_data_stage
from .retrieve_evidence import run_retrieve_evidence_stage
from .synthesize_brief_answer import run_synthesize_brief_answer_stage
from .synthesize_report import run_synthesize_report_stage


STAGE_RUNNERS = {
    "query_structured_data": run_query_structured_data_stage,
    "synthesize_brief_answer": run_synthesize_brief_answer_stage,
    "retrieve_evidence": run_retrieve_evidence_stage,
    "synthesize_report": run_synthesize_report_stage,
}


__all__ = [
    "STAGE_RUNNERS",
    "run_query_structured_data_stage",
    "run_synthesize_brief_answer_stage",
    "run_retrieve_evidence_stage",
    "run_synthesize_report_stage",
]
