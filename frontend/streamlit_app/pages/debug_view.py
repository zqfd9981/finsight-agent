from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_debug_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    routing: dict[str, object] = {}
    planning: dict[str, object] = {}
    execution: dict[str, object] = {"stage_statuses": {}, "stage_observations": []}
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            routing = dict(block.payload_summary)
        elif block.block_type == "planning":
            planning = dict(block.payload_summary)
        elif block.block_type == "execution":
            execution = dict(block.payload_summary)
    stages = list(execution.get("stage_observations", []))
    return {
        "routing": routing,
        "planning": planning,
        "execution": execution,
        "stages": stages,
        "response_type": envelope.response.response_type,
    }
