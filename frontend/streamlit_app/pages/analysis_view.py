from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_analysis_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    intent = ""
    strategy = ""
    evidence_ref_count = 0
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            intent = str(block.payload_summary.get("intent") or "")
        if block.block_type == "execution":
            observations = block.payload_summary.get("stage_observations", [])
            for item in observations:
                stage_name = item.get("stage_name", "")
                key_outputs = item.get("key_outputs", {})
                if stage_name == "collect_event_context":
                    strategy = str(key_outputs.get("strategy") or "")
                if stage_name == "retrieve_evidence":
                    evidence_ref_count = int(
                        key_outputs.get("evidence_ref_count") or 0
                    )
    return {
        "summary": getattr(envelope.response, "summary", ""),
        "response_type": envelope.response.response_type,
        "intent": intent,
        "strategy": strategy,
        "degraded": envelope.response.response_type != "success",
        "evidence_ref_count": evidence_ref_count,
        "session_id": envelope.session_id,
    }
